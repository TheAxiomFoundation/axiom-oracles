#!/usr/bin/env python3
"""Compute NZ RuleSpec closure against the pinned corpus release by citation path."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from nz_programs import PROGRAM_VIEWS  # noqa: E402
from nz_spine import NZSpineError, build_spine_frontier  # noqa: E402

OUT_DIR = REPO_ROOT / "closure" / "nz"
SOURCE_PATH = OUT_DIR / "source.json"
SUMMARY_PATH = OUT_DIR / "summary.json"
REQUEST_TRACE_PATH = (
    REPO_ROOT
    / "conformance"
    / "executable"
    / "nz-treasury-incomeexplorer"
    / "requests.json"
)
EVALUATION_TRACE_PATH = (
    REPO_ROOT / "comparisons" / "nz-treasury-incomeexplorer" / "evaluation-traces.json"
)
RATCHET_PATH = OUT_DIR / "denominator-ratchet.json"
INSTRUMENT_GRAPH_PATH = (
    REPO_ROOT / "conformance" / "closure" / "nz-instrument-graph.json"
)
INSTRUMENT_DISPOSITIONS_PATH = OUT_DIR / "instrument-dispositions.json"
DEPENDENCY_DISPOSITIONS_PATH = OUT_DIR / "dependency-dispositions.json"
SPINE_LEDGER_PATH = OUT_DIR / "spine-ledger.json"
SOURCE_COMPARISON_PATH = (
    REPO_ROOT / "comparisons" / "nz-treasury-incomeexplorer" / "source-comparison.json"
)
COMPILED_PROGRAM_PATH = (
    REPO_ROOT
    / "conformance"
    / "executable"
    / "nz-treasury-incomeexplorer"
    / "compiled-program.json"
)
SOURCE_SHA256 = "a69b872fbc9fd9a98132ea5b7f5272d8be9631d3060651603b2b3c1f7cd64aea"
SOURCE_COMPARISON_SHA256 = (
    "abd3bcbebc01c73e58c27496db5897a306bb0496ae1d53e5abbd5ae487010b3b"
)
COMPILED_PROGRAM_SHA256 = (
    "b1d72c1f4840a1774aefbddc9692e22a79ced26cde6c44efb4c01fc394a15c33"
)
EVALUATION_TRACE_SHA256 = (
    "43cca386b15e71fc07fa8fb223b2bef8d351e0bb56ecfdf05fe98e790e66f4da"
)
RULESPEC_REPO = Path("/Users/maxghenis/TheAxiomFoundation/rulespec-nz")
CORPUS_REPO = Path("/Users/maxghenis/TheAxiomFoundation/axiom-corpus")
RULESPEC_SHA = "89a7d25dc03a4d045348620283332de10b1047da"
CORPUS_RELEASE_REF = "origin/release/nz-rulespec-2026-07-18"
CORPUS_RELEASE_SHA = "3f7b5d985bce759cb487f1b7fd050f5cbf007d17"
ROOTS = ("nz/statutes", "nz/regulations", "nz/policies")
CORPUS_FILES = (
    "data/corpus/provisions/nz/statute/2026-06-16-rulespec-nz-pco.jsonl",
    "data/corpus/provisions/nz/regulation/2026-06-16-rulespec-nz-pco.jsonl",
    "data/corpus/provisions/nz/district-plan/2026-07-18-wellington-district-plan.jsonl",
)
LEDGER_REPO_PATH = "known-missing-money-atoms.yaml"
RATCHET_REPO_PATH = RATCHET_PATH.relative_to(REPO_ROOT).as_posix()

INSTRUMENT_GRAPH_SCHEMA = "axiom_oracles.closure.instrument_graph.v1"
INSTRUMENT_STATUSES = (
    "encoded",
    "classified-with-reason",
    "excluded-with-reason",
    "pending",
)
INSTRUMENT_RELATIONS = ("basis_for", "bears_on")
INSTRUMENT_ACTS = {
    "nz/statute/act/public/2001/0049": {
        "eli": "https://www.legislation.govt.nz/act/public/2001/49/en/latest/",
        "classic_listing_url": (
            "https://classic.legislation.govt.nz/act/public/2001/0049/latest/"
            "secondary.aspx?sds=aa&sdr=1&sda=1"
        ),
        "reported_count": 136,
        "programs": ("nz/acc-earners-levy",),
    },
    "nz/statute/act/public/2007/0097": {
        "eli": "https://www.legislation.govt.nz/act/public/2007/97/en/latest/",
        "classic_listing_url": (
            "https://classic.legislation.govt.nz/act/public/2007/0097/latest/"
            "secondary.aspx?sds=aa&sdr=1&sda=1"
        ),
        "reported_count": 202,
        "programs": (
            "nz/income-tax",
            "nz/independent-earner-tax-credit",
            "nz/working-for-families",
        ),
    },
    "nz/statute/act/public/2018/0032": {
        "eli": "https://www.legislation.govt.nz/act/public/2018/32/en/latest/",
        "classic_listing_url": (
            "https://classic.legislation.govt.nz/act/public/2018/0032/latest/"
            "secondary.aspx?sds=aa&sdr=1&sda=1"
        ),
        "reported_count": 99,
        "programs": (
            "nz/accommodation-supplement",
            "nz/main-benefits",
            "nz/winter-energy-payment",
        ),
    },
}
PROGRAM_INSTRUMENT_ACT = {
    program: act_path
    for act_path, act in INSTRUMENT_ACTS.items()
    for program in act["programs"]
}

# The read-only exact-title citation pass found 20 distinct source instruments.
# Every source is deliberately mapped to an existing graph row, one of the
# three governing spine roots, or a supplemental frontier row.  This is an
# audited coverage ratchet for the approximation receipt; it does not pretend
# to be the not-yet-available axiom-corpus#611 NZ citation extractor.
CITATION_SCAN_SOURCE_DISPOSITIONS = (
    {
        "source_id": "act/public/1973/0005",
        "title": "Rates Rebate Act 1973",
        "source_target_match_rows": 2,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/act/public/1973/5/en/latest/",
    },
    {
        "source_id": "act/public/1985/0141",
        "title": "Goods and Services Tax Act 1985",
        "source_target_match_rows": 24,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/act/public/1985/141/en/latest/",
    },
    {
        "source_id": "act/public/1987/0129",
        "title": "Parental Leave and Employment Protection Act 1987",
        "source_target_match_rows": 6,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/act/public/1987/129/en/latest/",
    },
    {
        "source_id": "act/public/1991/0142",
        "title": "Child Support Act 1991",
        "source_target_match_rows": 21,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/act/public/1991/142/en/latest/",
    },
    {
        "source_id": "act/public/1992/0076",
        "title": "Public and Community Housing Management Act 1992",
        "source_target_match_rows": 18,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/act/public/1992/76/en/latest/",
    },
    {
        "source_id": "act/public/1994/0166",
        "title": "Tax Administration Act 1994",
        "source_target_match_rows": 274,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/act/public/1994/166/en/latest/",
    },
    {
        "source_id": "act/public/2001/0049",
        "title": "Accident Compensation Act 2001",
        "source_target_match_rows": 23,
        "resolution": "spine_root",
        "frontier_ref": "nz/statute/act/public/2001/0049",
    },
    {
        "source_id": "act/public/2001/0084",
        "title": "New Zealand Superannuation and Retirement Income Act 2001",
        "source_target_match_rows": 25,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/act/public/2001/84/en/latest/",
    },
    {
        "source_id": "act/public/2006/0040",
        "title": "KiwiSaver Act 2006",
        "source_target_match_rows": 31,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/act/public/2006/40/en/latest/",
    },
    {
        "source_id": "act/public/2007/0097",
        "title": "Income Tax Act 2007",
        "source_target_match_rows": 28,
        "resolution": "spine_root",
        "frontier_ref": "nz/statute/act/public/2007/0097",
    },
    {
        "source_id": "act/public/2009/0051",
        "title": "Immigration Act 2009",
        "source_target_match_rows": 2,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/act/public/2009/51/en/latest/",
    },
    {
        "source_id": "act/public/2011/0062",
        "title": "Student Loan Scheme Act 2011",
        "source_target_match_rows": 18,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/act/public/2011/62/en/latest/",
    },
    {
        "source_id": "act/public/2018/0004",
        "title": "Customs and Excise Act 2018",
        "source_target_match_rows": 8,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/act/public/2018/4/en/latest/",
    },
    {
        "source_id": "act/public/2018/0032",
        "title": "Social Security Act 2018",
        "source_target_match_rows": 26,
        "resolution": "spine_root",
        "frontier_ref": "nz/statute/act/public/2018/0032",
    },
    {
        "source_id": "act/public/2026/0008",
        "title": "Taxation (Annual Rates for 2025–26, Compliance Simplification, and Remedial Measures) Act 2026",
        "source_target_match_rows": 20,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/act/public/2026/8/en/latest/",
    },
    {
        "source_id": "regulation/public/1993/0169",
        "title": "Health Entitlement Cards Regulations 1993",
        "source_target_match_rows": 7,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/1993/169/en/latest/",
    },
    {
        "source_id": "regulation/public/1998/0277",
        "title": "Student Allowances Regulations 1998",
        "source_target_match_rows": 5,
        "resolution": "supplemental",
        "frontier_ref": "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/1998/277/en/latest/",
    },
    {
        "source_id": "regulation/public/2018/0202",
        "title": "Social Security Regulations 2018",
        "source_target_match_rows": 17,
        "resolution": "instrument_graph",
        "frontier_ref": "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2018/202/en/latest/",
    },
    {
        "source_id": "regulation/public/2025/0018",
        "title": "Accident Compensation (Earners’ Levy) Regulations 2025",
        "source_target_match_rows": 1,
        "resolution": "instrument_graph",
        "frontier_ref": "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2025/18/en/latest/",
    },
    {
        "source_id": "regulation/public/2026/0036",
        "title": "Social Security (Rates of Benefits and Allowances) Order 2026",
        "source_target_match_rows": 4,
        "resolution": "instrument_graph",
        "frontier_ref": "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2026/36/en/latest/",
    },
)

CITATION_SCAN_DISTINCT_SOURCE_PATH_COUNTS = {
    "act/public/1973/0005": 1,
    "act/public/1985/0141": 23,
    "act/public/1987/0129": 6,
    "act/public/1991/0142": 19,
    "act/public/1992/0076": 17,
    "act/public/1994/0166": 267,
    "act/public/2001/0049": 23,
    "act/public/2001/0084": 23,
    "act/public/2006/0040": 30,
    "act/public/2007/0097": 25,
    "act/public/2009/0051": 2,
    "act/public/2011/0062": 16,
    "act/public/2018/0004": 8,
    "act/public/2018/0032": 25,
    "act/public/2026/0008": 20,
    "regulation/public/1993/0169": 5,
    "regulation/public/1998/0277": 3,
    "regulation/public/2018/0202": 17,
    "regulation/public/2025/0018": 1,
    "regulation/public/2026/0036": 4,
}

TRACE_SCHEMA = "axiom_oracles.nz_evaluation_traces.v1"
TRACE_SUITE = "nz-treasury-incomeexplorer"
TRACE_EVALUATION_COUNT = 883
TRACE_ENGINE = {
    "binary_sha256": "56fbffea1e0e32c52b6fcbddbca76223bb185b33b49368c288e0c7213b0126e1",
    "git_sha": "d59969b53430ae2fd97eb4349d44ad23ce930d85",
}
TRACE_COMPILED_PROGRAM = {
    "artifact_sha256": "b1d72c1f4840a1774aefbddc9692e22a79ced26cde6c44efb4c01fc394a15c33",
    "derived_outputs": 176,
    "engine_evaluations": TRACE_EVALUATION_COUNT,
    "input_slots": 328,
    "parameters": 129,
    "relations": 0,
}
TRACE_CAPTURE = {
    "lineage_mode": "attested",
    "source_comparison": {
        "artifact": "comparisons/nz-treasury-incomeexplorer/source-comparison.json",
        "regenerated_sha256": (
            "7b58fcfdb50f8627f0228bf024d95cde3ef3d50caae7f2d9de2862d82ea6e8c6"
        ),
        "regeneration_difference": "provenance only",
        "sha256": "abd3bcbebc01c73e58c27496db5897a306bb0496ae1d53e5abbd5ae487010b3b",
        "substance_sha256": (
            "a52a16d81433c91bc73e107fdaa5cdbc701d908f5c359615fd317cb82e6b8a15"
        ),
    },
    "source_harness": {
        "path": "nz-lane/emtr_reproduction/run.py",
        "repository": "TheAxiomFoundation/ops",
        "repository_commit": "bcf631b59968be4907e679b4704f5e029e2188ab",
        "repository_commit_status": "pinned",
        "sha256": "9aa0fc64af8dca4a8f7574e98923fe0022561679027c2ed5325bf381e9c6ab27",
    },
}

REQUEST_EVIDENCE_PROVENANCE = {
    "compiled_sha256": TRACE_COMPILED_PROGRAM["artifact_sha256"],
    "engine_binary_sha256": TRACE_ENGINE["binary_sha256"],
    "engine_git_sha": TRACE_ENGINE["git_sha"],
    "harness": "TheAxiomFoundation/ops/nz-lane/emtr_reproduction/run.py",
    "harness_commit": "bcf631b5",
    "rulespec_commit": RULESPEC_SHA,
}


class ClosureError(ValueError):
    pass


def _citation_scan_source_dispositions() -> list[dict[str, Any]]:
    source_ids = {str(row["source_id"]) for row in CITATION_SCAN_SOURCE_DISPOSITIONS}
    if source_ids != set(CITATION_SCAN_DISTINCT_SOURCE_PATH_COUNTS):
        raise ClosureError("NZ citation-scan distinct-path source coverage drifted")
    rows = [
        {
            **dict(row),
            "distinct_source_provision_paths": (
                CITATION_SCAN_DISTINCT_SOURCE_PATH_COUNTS[str(row["source_id"])]
            ),
        }
        for row in CITATION_SCAN_SOURCE_DISPOSITIONS
    ]
    if (
        sum(int(row["source_target_match_rows"]) for row in rows) != 560
        or sum(int(row["distinct_source_provision_paths"]) for row in rows) != 535
    ):
        raise ClosureError("NZ citation-scan hit/path count ratchet drifted")
    return rows


class ClosureValidation(dict):
    """Mapping-compatible validation result with the DK producer attributes.

    The current NZ certificate adapter consumes program-scoped mappings while
    d3/instrument-frontier's common adapter consumes ``summary.closed``.  A
    dict subclass exposes both without changing either enforcement path.
    """

    @property
    def closed(self) -> bool:
        return self.get("closed") is True


class ClosureVerificationResult:
    """Small DK-compatible result for full producer verification."""

    def __init__(
        self,
        *,
        document: dict[str, Any] | None,
        expected: dict[str, Any] | None,
        errors: tuple[str, ...],
    ) -> None:
        self.document = document
        self.expected = expected
        self.errors = errors

    @property
    def valid(self) -> bool:
        return not self.errors


def _git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if process.returncode:
        raise ClosureError(process.stderr.strip() or process.stdout.strip())
    return process.stdout


def _citations(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "corpus_citation_path" and isinstance(child, str):
                found.add(child)
            found.update(_citations(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_citations(child))
    return found


def _formula_texts(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "formula" and isinstance(child, str):
                found.append(child)
            else:
                found.extend(_formula_texts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_formula_texts(child))
    return found


def _list_sha256(values: list[str]) -> str:
    raw = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _node_id(path: str, name: str) -> str:
    module = path.removeprefix("nz/").removesuffix(".yaml")
    return f"nz:{module}#{name}"


def load_source() -> dict:
    """Load the versioned denominator only when its review pin still matches."""

    try:
        raw = SOURCE_PATH.read_bytes()
        if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
            raise ClosureError(
                "NZ closure source bytes changed; review and re-pin the denominator"
            )
        source = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read the NZ closure source: {exc}") from exc
    if not isinstance(source, dict):
        raise ClosureError("NZ closure source must contain an object")
    return source


def _load_json_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ClosureError(f"{label} must contain an object")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


_INSTRUMENT_ROW_REQUIRED = {
    "eli",
    "relation",
    "date_document",
    "type_document",
    "in_force",
    "title",
    "title_short",
    "act_eli",
    "act_citation_path",
}
_INSTRUMENT_ROW_OPTIONAL = {
    "empowering_provisions",
    "corpus_citation_path",
    "corpus_commit",
    "corpus_manifest",
    "corpus_manifest_sha256",
    "source_sha256",
    "retrieval_method",
    "publisher_response_sha256",
    "publisher_response_retrieved_at",
    "application_end",
}
_DISPOSITION_OPTIONAL = {
    "classification",
    "reason",
    "bearing",
    "encoded_by",
    "bears_on_computed_surface",
    "defining_provision",
    "size_class",
    "target_module",
}


def _load_instrument_graph() -> tuple[dict[str, Any], bytes]:
    try:
        raw = INSTRUMENT_GRAPH_PATH.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read NZ instrument graph: {exc}") from exc
    if not isinstance(document, dict):
        raise ClosureError("NZ instrument graph must contain an object")
    if set(document) != {
        "schema",
        "schema_compatibility_note",
        "act_eli",
        "act_citation_path",
        "retrieved_at",
        "retrieval_method",
        "retrieval_receipts",
        "instruments",
    }:
        raise ClosureError(
            "NZ instrument graph has unexpected or missing top-level keys"
        )
    if document.get("schema") != INSTRUMENT_GRAPH_SCHEMA:
        raise ClosureError("unexpected NZ instrument graph schema")
    note = document.get("schema_compatibility_note")
    if not isinstance(note, str) or "single-Act" not in note:
        raise ClosureError(
            "NZ instrument graph must disclose its v1 multi-Act extension"
        )
    retrieved_at = document.get("retrieved_at")
    if not isinstance(retrieved_at, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", retrieved_at
    ):
        raise ClosureError("NZ instrument graph retrieved_at must be an ISO date")
    retrieval_method = document.get("retrieval_method")
    if not isinstance(retrieval_method, str) or not retrieval_method.strip():
        raise ClosureError("NZ instrument graph retrieval_method must be non-empty")
    if set(document.get("act_citation_path") or ()) != set(INSTRUMENT_ACTS):
        raise ClosureError("NZ instrument graph empowering-Act paths drifted")
    expected_elis = {str(value["eli"]) for value in INSTRUMENT_ACTS.values()}
    if set(document.get("act_eli") or ()) != expected_elis:
        raise ClosureError("NZ instrument graph empowering-Act ELIs drifted")

    rows = document.get("instruments")
    if not isinstance(rows, list) or not rows:
        raise ClosureError("NZ instrument graph has no instrument rows")
    seen: set[str] = set()
    sort_keys: list[tuple[str, str, str]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ClosureError(f"NZ instrument graph row {index} is not an object")
        keys = set(row)
        if not _INSTRUMENT_ROW_REQUIRED.issubset(keys) or not keys.issubset(
            _INSTRUMENT_ROW_REQUIRED | _INSTRUMENT_ROW_OPTIONAL
        ):
            raise ClosureError(
                f"NZ instrument graph row {index} has unexpected or missing keys"
            )
        eli = row.get("eli")
        if not isinstance(eli, str) or not eli.startswith("https://"):
            raise ClosureError(f"NZ instrument graph row {index} has invalid ELI/URL")
        if eli in seen:
            raise ClosureError(f"duplicate NZ instrument ELI/URL {eli!r}")
        seen.add(eli)
        if row.get("relation") not in INSTRUMENT_RELATIONS:
            raise ClosureError(f"{eli}: unsupported instrument relation")
        if row["relation"] == "basis_for" and not re.fullmatch(
            r"https://www\.legislation\.govt\.nz/"
            r"(?:secondary-legislation/(?:agency|pco)-drafted|regulation/public)/"
            r"[^/]+/[^/]+/en/latest/",
            eli,
        ):
            raise ClosureError(f"{eli}: basis_for row is not a canonical NZ ELI")
        if row["relation"] == "bears_on":
            if not re.match(
                r"https://(?:www\.(?:ird\.govt\.nz|workandincome\.govt\.nz|"
                r"acc\.co\.nz|taxtechnical\.ird\.govt\.nz)|"
                r"taxtechnical\.ird\.govt\.nz)/",
                eli,
            ):
                raise ClosureError(f"{eli}: supplemental publisher is not allowlisted")
            row_method = row.get("retrieval_method")
            if not isinstance(row_method, str) or not row_method.strip():
                raise ClosureError(f"{eli}: supplemental retrieval method is missing")
            publisher_digest = row.get("publisher_response_sha256")
            publisher_retrieved_at = row.get("publisher_response_retrieved_at")
            if (publisher_digest is None) != (publisher_retrieved_at is None):
                raise ClosureError(
                    f"{eli}: live publisher receipt must carry both digest and date"
                )
            if publisher_digest is not None and (
                not re.fullmatch(r"[0-9a-f]{64}", str(publisher_digest))
                or not isinstance(publisher_retrieved_at, str)
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", publisher_retrieved_at)
            ):
                raise ClosureError(f"{eli}: live publisher receipt is malformed")
            corpus_path = row.get("corpus_citation_path")
            if corpus_path is not None:
                if not isinstance(corpus_path, str) or not corpus_path.startswith(
                    "nz/guidance/"
                ):
                    raise ClosureError(f"{eli}: invalid corpus guidance citation path")
                if not re.fullmatch(r"[0-9a-f]{40}", str(row.get("corpus_commit", ""))):
                    raise ClosureError(f"{eli}: corpus guidance commit is not pinned")
                if (
                    not isinstance(row.get("corpus_manifest"), str)
                    or not row["corpus_manifest"].strip()
                ):
                    raise ClosureError(f"{eli}: corpus guidance manifest is missing")
                if not re.fullmatch(
                    r"[0-9a-f]{64}", str(row.get("corpus_manifest_sha256", ""))
                ):
                    raise ClosureError(f"{eli}: corpus manifest bytes are not bound")
                if "source_sha256" in row and not re.fullmatch(
                    r"[0-9a-f]{64}", str(row["source_sha256"])
                ):
                    raise ClosureError(f"{eli}: corpus source digest is invalid")
        act_path = row.get("act_citation_path")
        act = INSTRUMENT_ACTS.get(str(act_path))
        if act is None or row.get("act_eli") != act["eli"]:
            raise ClosureError(f"{eli}: empowering-Act identity is inconsistent")
        if not isinstance(row.get("in_force"), bool):
            raise ClosureError(f"{eli}: in_force must be boolean")
        for field in ("date_document", "type_document", "title", "title_short"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ClosureError(f"{eli}: {field} must be a non-empty string")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date_document"]):
            raise ClosureError(f"{eli}: date_document must be an ISO date")
        if "application_end" in row and not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", str(row["application_end"])
        ):
            raise ClosureError(f"{eli}: application_end must be an ISO date")
        if "application_end" in row and (
            row["relation"] != "bears_on"
            or row["in_force"] is not False
            or str(row["application_end"]) >= retrieved_at
        ):
            raise ClosureError(
                f"{eli}: expired application period is inconsistent with capture date"
            )
        if row["relation"] == "basis_for" and (
            not isinstance(row.get("empowering_provisions"), str)
            or not row["empowering_provisions"].strip()
        ):
            raise ClosureError(f"{eli}: empowering provisions were not captured")
        sort_keys.append((str(act_path), str(row["relation"]), eli))
    if sort_keys != sorted(sort_keys):
        raise ClosureError("NZ instrument graph rows are not canonically sorted")

    receipts = document.get("retrieval_receipts")
    if not isinstance(receipts, list) or len(receipts) != len(INSTRUMENT_ACTS):
        raise ClosureError("NZ instrument graph retrieval receipts are incomplete")
    receipts_by_act: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise ClosureError("NZ instrument graph receipt is not an object")
        act_path = receipt.get("act_citation_path")
        if (
            not isinstance(act_path, str)
            or act_path not in INSTRUMENT_ACTS
            or act_path in receipts_by_act
        ):
            raise ClosureError("NZ instrument graph receipt Act identity is invalid")
        reported = receipt.get("reported_count")
        captured = receipt.get("captured_count")
        unresolved = receipt.get("unresolved_count")
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (reported, captured, unresolved)
        ):
            raise ClosureError(f"{act_path}: invalid instrument receipt counts")
        actual = sum(
            row["relation"] == "basis_for" and row["act_citation_path"] == act_path
            for row in rows
        )
        if captured != actual or reported != captured + unresolved:
            raise ClosureError(
                f"{act_path}: instrument receipt counts do not reconcile"
            )
        act = INSTRUMENT_ACTS[act_path]
        if (
            receipt.get("act_eli") != act["eli"]
            or receipt.get("listing_url") != act["eli"]
            or receipt.get("classic_cross_check_url") != act["classic_listing_url"]
            or reported != act["reported_count"]
        ):
            raise ClosureError(
                f"{act_path}: authoritative retrieval URLs/count drifted"
            )
        method = receipt.get("method")
        if not isinstance(method, str) or not method.strip():
            raise ClosureError(f"{act_path}: retrieval receipt method is missing")
        complete = receipt.get("complete")
        if not isinstance(complete, bool) or complete != (unresolved == 0):
            raise ClosureError(f"{act_path}: instrument receipt completeness is stale")
        digest_field = "response_sha256" if complete else "manifest_sha256"
        if not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get(digest_field, ""))):
            raise ClosureError(f"{act_path}: retrieval receipt bytes are not SHA-bound")
        if not complete:
            if (
                not isinstance(receipt.get("manifest_name"), str)
                or not receipt["manifest_name"].strip()
            ):
                raise ClosureError(f"{act_path}: offline manifest name is missing")
            manifest_discovered = receipt.get("manifest_discovered_count")
            manifest_downloaded = receipt.get("manifest_downloaded_count")
            manifest_failed = receipt.get("manifest_failed_count")
            if (
                not all(
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and value >= 0
                    for value in (
                        manifest_discovered,
                        manifest_downloaded,
                        manifest_failed,
                    )
                )
                or manifest_discovered != manifest_downloaded + manifest_failed
            ):
                raise ClosureError(
                    f"{act_path}: offline manifest totals do not reconcile"
                )
            failed_work_ids = receipt.get("manifest_failed_work_ids")
            if (
                not isinstance(failed_work_ids, list)
                or failed_work_ids != sorted(set(failed_work_ids))
                or len(failed_work_ids) != manifest_failed
                or not all(
                    isinstance(value, str) and value for value in failed_work_ids
                )
            ):
                raise ClosureError(
                    f"{act_path}: offline manifest failures are malformed"
                )
            for field in ("source_retrieved_at", "status_evaluated_as_of"):
                value = receipt.get(field)
                if not isinstance(value, str) or not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}", value
                ):
                    raise ClosureError(f"{act_path}: {field} must be an ISO date")
        receipts_by_act[act_path] = receipt
    return document, raw


def _load_instrument_dispositions() -> tuple[dict[str, Any], bytes]:
    try:
        raw = INSTRUMENT_DISPOSITIONS_PATH.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read NZ instrument dispositions: {exc}") from exc
    if not isinstance(document, dict):
        raise ClosureError("NZ instrument dispositions must contain an object")
    if set(document) != {
        "schema",
        "schema_compatibility_note",
        "instrument_dispositions",
        "supplemental_instruments",
        "discovery_receipts",
    }:
        raise ClosureError(
            "NZ instrument dispositions have unexpected or missing top-level keys"
        )
    if document.get("schema") != "axiom_oracles.nz_instrument_dispositions.v3":
        raise ClosureError("unexpected NZ instrument disposition schema")
    note = document.get("schema_compatibility_note")
    if not isinstance(note, str) or "repeated per program" not in note:
        raise ClosureError(
            "NZ instrument dispositions must disclose their program-scoped extension"
        )
    rows = document.get("instrument_dispositions")
    if not isinstance(rows, list):
        raise ClosureError("NZ instrument dispositions must contain a row list")
    if not isinstance(document.get("supplemental_instruments"), list):
        raise ClosureError("NZ instrument dispositions lack supplemental instruments")
    if not isinstance(document.get("discovery_receipts"), dict):
        raise ClosureError("NZ instrument dispositions lack discovery receipts")
    return document, raw


def _load_dependency_dispositions() -> tuple[dict[str, Any], bytes]:
    try:
        raw = DEPENDENCY_DISPOSITIONS_PATH.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read NZ dependency dispositions: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "scope_receipts",
        "encoded_dependencies",
        "input_grounding",
    }:
        raise ClosureError(
            "NZ dependency dispositions have unexpected or missing top-level keys"
        )
    if document.get("schema") != "axiom_oracles.nz_dependency_dispositions.v1":
        raise ClosureError("unexpected NZ dependency disposition schema")
    if not isinstance(document.get("scope_receipts"), dict):
        raise ClosureError("NZ dependency dispositions lack scope receipts")
    if not isinstance(document.get("input_grounding"), list):
        raise ClosureError("NZ dependency dispositions lack input grounding rows")
    if not isinstance(document.get("encoded_dependencies"), list):
        raise ClosureError("NZ dependency dispositions lack encoded dependency rows")
    return document, raw


def _load_spine_ledger() -> tuple[dict[str, Any], bytes]:
    try:
        raw = SPINE_LEDGER_PATH.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read NZ spine ledger: {exc}") from exc
    if not isinstance(document, dict):
        raise ClosureError("NZ spine ledger must contain an object")
    return document, raw


def _load_source_comparison_catalog() -> tuple[dict[str, Any], bytes]:
    try:
        raw = SOURCE_COMPARISON_PATH.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read NZ source comparison: {exc}") from exc
    if hashlib.sha256(raw).hexdigest() != SOURCE_COMPARISON_SHA256:
        raise ClosureError("NZ source-comparison dependency receipt drifted")
    if not isinstance(document, dict):
        raise ClosureError("NZ source comparison must contain an object")
    return document, raw


def _reached_compiled_inputs() -> set[str]:
    try:
        raw = COMPILED_PROGRAM_PATH.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read NZ compiled program: {exc}") from exc
    if hashlib.sha256(raw).hexdigest() != COMPILED_PROGRAM_SHA256:
        raise ClosureError("NZ compiled-program dependency receipt drifted")
    program = document.get("program") if isinstance(document, dict) else None
    derived_rows = program.get("derived") if isinstance(program, dict) else None
    if not isinstance(derived_rows, list) or len(derived_rows) != 176:
        raise ClosureError("NZ compiled program must contain 176 derived rules")
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for row in derived_rows:
        rule_id = row.get("id") if isinstance(row, dict) else None
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("name"), str)
            or not isinstance(row.get("expr"), dict)
            or (rule_id is not None and not isinstance(rule_id, str))
            or (isinstance(rule_id, str) and rule_id in by_id)
            or row["name"] in by_name
        ):
            raise ClosureError("NZ compiled derived-rule inventory is malformed")
        if isinstance(rule_id, str):
            by_id[rule_id] = row
        by_name[row["name"]] = row
    anonymous = sorted(row["name"] for row in derived_rows if row.get("id") is None)
    if anonymous != [
        "best_start_family_scheme_income_for_relationship_period",
        "wff_family_scheme_income_for_relationship_period",
    ]:
        raise ClosureError("NZ compiled composition-output inventory drifted")

    reached_rules: set[str] = set()
    reached_inputs: set[str] = set()

    def walk_expr(value: Any, *, owner: str) -> None:
        if isinstance(value, dict):
            kind = value.get("kind")
            if kind == "input":
                name = value.get("name")
                if not isinstance(name, str) or not name:
                    raise ClosureError(f"{owner}: malformed compiled input reference")
                reached_inputs.add(name)
            elif kind == "derived":
                name = value.get("name")
                target = by_name.get(name) if isinstance(name, str) else None
                if target is None:
                    raise ClosureError(f"{owner}: missing compiled derived dependency")
                visit_rule(target)
            for child in value.values():
                walk_expr(child, owner=owner)
        elif isinstance(value, list):
            for child in value:
                walk_expr(child, owner=owner)

    def visit_rule(row: dict[str, Any]) -> None:
        rule_id = row.get("id") or f"composition:{row['name']}"
        if rule_id in reached_rules:
            return
        reached_rules.add(rule_id)
        walk_expr(row["expr"], owner=rule_id)

    roots = sorted({root for spec in PROGRAM_VIEWS.values() for root in spec["roots"]})
    for root in roots:
        row = by_id.get(root)
        if row is None:
            raise ClosureError(f"NZ compiled program lacks requested root {root}")
        visit_rule(row)
    if len(reached_rules) != 77 or len(reached_inputs) != 147:
        raise ClosureError(
            "NZ compiled requested-root reachability denominator drifted from 77 derived rules / 147 inputs"
        )
    return reached_inputs


def _expected_dependency_inputs(
    source_comparison: Mapping[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    catalog = source_comparison.get("exercise_input_catalog")
    if not isinstance(catalog, dict) or len(catalog) != 328:
        raise ClosureError("NZ exercise input catalog must contain 328 slots")
    state_counts = {"constant": 0, "varied": 0, "not_supplied": 0}
    supplied: set[str] = set()
    for name, value in sorted(catalog.items()):
        if not isinstance(name, str) or not isinstance(value, dict):
            raise ClosureError("NZ exercise input catalog is malformed")
        state = value.get("state")
        if state not in state_counts:
            raise ClosureError(f"{name}: invalid exercise-input state")
        state_counts[state] += 1
        if state == "not_supplied":
            continue
        supplied.add(name)
        canonical = value.get("canonical_request_name")
        if not isinstance(canonical, str) or "#input." not in canonical:
            raise ClosureError(f"{name}: invalid canonical request name")
        expected[("engine_request", name)] = {
            "canonical_request_name": canonical,
            "observed_state": state,
            "target_module": canonical.split("#", 1)[0].replace(":", "/") + ".yaml",
        }
    if state_counts != {"constant": 98, "varied": 52, "not_supplied": 178}:
        raise ClosureError("NZ exercise-input state denominator drifted")
    reached = _reached_compiled_inputs()
    harness_only = sorted(supplied - reached)
    if not reached.issubset(supplied) or harness_only != [
        "child_tax_credit_for_entitlement_period",
        "parental_tax_credit_additional_abatement",
        "parental_tax_credit_for_entitlement_period",
    ]:
        raise ClosureError(
            "NZ composition/harness input union drifted from 147 reached plus three harness-only slots"
        )
    latent_law = {name for group in _latent_law_groups() for name in group["names"]}
    latent_world = set(_latent_world_reasons())
    if latent_law & latent_world or len(latent_law) != 69 or len(latent_world) != 30:
        raise ClosureError("NZ latent eligibility audit must partition 99 inputs")
    for name in sorted(latent_law | latent_world):
        value = catalog.get(name)
        if not isinstance(value, dict) or value.get("state") != "not_supplied":
            raise ClosureError(
                f"NZ latent eligibility input {name} is not an omitted compiled slot"
            )
        canonical = value.get("canonical_request_name")
        if not isinstance(canonical, str) or "#input." not in canonical:
            raise ClosureError(
                f"NZ latent eligibility input {name} lacks a canonical name"
            )
        expected[("implicit_legal_surface", name)] = {
            "canonical_request_name": canonical,
            "observed_state": "not_supplied",
            "target_module": canonical.split("#", 1)[0].replace(":", "/") + ".yaml",
        }
    expected[("host_rule", "ORACLE_IWTC_WEEKLY_THRESHOLD")] = {
        "declared_value": "1226.7 / 52.2",
    }

    closures = source_comparison.get("declared_eligibility_closures")
    choices = closures.get("choices") if isinstance(closures, dict) else None
    if not isinstance(choices, dict) or set(choices) != {
        "care",
        "gates",
        "residence",
        "work_tests",
    }:
        raise ClosureError("NZ declared eligibility closures are malformed")
    for group, values in sorted(choices.items()):
        if not isinstance(values, dict):
            raise ClosureError(f"NZ eligibility closure group {group} is malformed")
        for name, value in sorted(values.items()):
            expected[("eligibility_closure", f"{group}.{name}")] = {
                "declared_value": value,
            }

    scenarios = source_comparison.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ClosureError("NZ source comparison lacks scenario inputs")
    scenario_names: set[str] = set()
    for scenario in scenarios:
        inputs = scenario.get("inputs") if isinstance(scenario, dict) else None
        if not isinstance(inputs, dict):
            raise ClosureError("NZ scenario input row is malformed")
        scenario_names.update(str(name) for name in inputs)
        if not isinstance(scenario.get("sampled_weekly_wages"), list):
            raise ClosureError("NZ scenario lacks sampled weekly wages")
    scenario_names.add("sampled_weekly_wage1")
    for name in sorted(scenario_names):
        expected[("scenario", name)] = {}
    if sum(key[0] == "engine_request" for key in expected) != 150:
        raise ClosureError("NZ consumed request-input denominator is not 150")
    if sum(key[0] == "eligibility_closure" for key in expected) != 27:
        raise ClosureError("NZ eligibility-closure denominator is not 27")
    if sum(key[0] == "scenario" for key in expected) != 11:
        raise ClosureError("NZ scenario-input denominator is not 11")
    if sum(key[0] == "implicit_legal_surface" for key in expected) != 99:
        raise ClosureError("NZ omitted legal-gate denominator is not 99")
    if len(expected) != 288:
        raise ClosureError("NZ typed dependency denominator is not 288")
    return expected


def _dependency_scope_receipts() -> dict[str, Any]:
    return {
        "composition": {
            "path": "nz-lane/emtr_reproduction/composition.yaml",
            "repository": "TheAxiomFoundation/ops",
            "repository_commit": "bcf631b59968be4907e679b4704f5e029e2188ab",
            "sha256": "af2ce73f1b16a74603965db1da92991545838748e943f3ed81cef394d469c3b0",
        },
        "compiled_program": {
            "path": str(COMPILED_PROGRAM_PATH.relative_to(REPO_ROOT)),
            "sha256": COMPILED_PROGRAM_SHA256,
        },
        "denominator": {
            "compiled_input_slots": 328,
            "compiled_requested_subgraph_derived_rules": 77,
            "declared_output_subgraph_reached_inputs": 147,
            "harness_supplied_inputs": 150,
            "harness_only_inputs": [
                "child_tax_credit_for_entitlement_period",
                "parental_tax_credit_additional_abatement",
                "parental_tax_credit_for_entitlement_period",
            ],
            "not_supplied_outside_declared_output_subgraph": 178,
            "semantically_upstream_omitted_legal_surface": 99,
            "remaining_compiled_slots_outside_claim": 79,
            "eligibility_closure_choices": 27,
            "scenario_inputs": 11,
            "host_rule_shortcuts": 1,
            "typed_grounding_rows": 288,
        },
        "eligibility_closures": {
            "path": "nz-lane/emtr_reproduction/eligibility-closures.json",
            "repository": "TheAxiomFoundation/ops",
            "repository_commit": "bcf631b59968be4907e679b4704f5e029e2188ab",
            "sha256": "a13881f452031d2875becb5a44d008da1dff5db0c001c5f3df959cfb69ed0324",
        },
        "harness": {
            "path": "nz-lane/emtr_reproduction/run.py",
            "repository": "TheAxiomFoundation/ops",
            "repository_commit": "bcf631b59968be4907e679b4704f5e029e2188ab",
            "sha256": "9aa0fc64af8dca4a8f7574e98923fe0022561679027c2ed5325bf381e9c6ab27",
        },
        "source_comparison": {
            "path": str(SOURCE_COMPARISON_PATH.relative_to(REPO_ROOT)),
            "sha256": SOURCE_COMPARISON_SHA256,
        },
    }


def _encoded_dependency_inventory() -> list[dict[str, Any]]:
    """Encoded values consumed by the host composition, outside leaf typing.

    These rows are not legal leaves: the engine derives them from the typed
    inputs below or selects them from source-bound RuleSpec parameters.  They
    are still enumerated so the composition/harness surface is complete.
    """

    modules: dict[str, tuple[str, tuple[str, ...]]] = {
        "nz/statutes/income_tax/schedule_1/individual_income_tax.yaml": (
            "compiled_parameter",
            (
                "individual_income_tax_bracket_rates",
                "individual_income_tax_bracket_thresholds",
            ),
        ),
        "nz/statutes/income_tax/family_scheme/tax_credits.yaml": (
            "compiled_parameter",
            (
                "best_start_abatement_rate",
                "best_start_abatement_threshold",
                "family_tax_credit_eldest_child_annual_amount",
                "wff_family_credit_abatement_rate",
                "wff_family_credit_abatement_threshold",
            ),
        ),
        "nz/statutes/income_tax/credits/individual_credits.yaml": (
            "compiled_parameter",
            (
                "independent_earner_tax_credit_abatement_rate",
                "independent_earner_tax_credit_abatement_threshold",
                "independent_earner_tax_credit_full_year_amount",
                "independent_earner_tax_credit_minimum_net_income",
            ),
        ),
        "nz/statutes/social_security/main_benefits/rates.yaml": (
            "compiled_parameter",
            (
                "jobseeker_support_single_with_dependent_children_weekly_rate",
                "main_benefit_income_test_3_abatement_rate",
                "main_benefit_income_test_lower_weekly_threshold",
            ),
        ),
    }
    outputs: dict[str, tuple[str, ...]] = {
        "nz/statutes/income_tax/schedule_1/individual_income_tax.yaml": (
            "individual_income_tax_before_credits",
        ),
        "nz/regulations/acc/earners_levy.yaml": (
            "acc_standard_earners_levy_including_gst",
        ),
        "nz/statutes/social_security/main_benefits/rates.yaml": (
            "jobseeker_support_net_weekly_payment",
            "sole_parent_support_net_weekly_payment",
        ),
        "nz/statutes/income_tax/family_scheme/tax_credits.yaml": (
            "best_start_credit_abatement",
            "best_start_tax_credit",
            "best_start_tax_credit_before_abatement",
            "family_tax_credit_after_abatement",
            "family_tax_credit_before_abatement",
            "in_work_tax_credit_before_abatement",
            "minimum_family_tax_credit",
            "wff_abatement_remaining_after_family_tax_credit",
        ),
        "nz/statutes/income_tax/family_scheme/eligibility.yaml": (
            "entitled_to_in_work_tax_credit",
        ),
        "nz/statutes/income_tax/credits/individual_credits.yaml": (
            "independent_earner_tax_credit",
        ),
        "nz/statutes/social_security/winter_energy_payment/core.yaml": (
            "winter_energy_payment_rate_per_winter_period",
        ),
        "nz/statutes/social_security/accommodation_supplement/core.yaml": (
            "accommodation_supplement_rounded_weekly_payment",
            "accommodation_supplement_weekly_amount_before_rounding",
            "accommodation_supplement_weekly_qualifying_accommodation_costs",
        ),
        "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml": (
            "family_scheme_income",
        ),
    }
    rows: list[dict[str, Any]] = []
    for module, (surface, names) in modules.items():
        for name in names:
            rows.append(
                {
                    "source_surface": surface,
                    "name": name,
                    "classification": "encoded",
                    "encoded_by": module,
                    "reason": "The pinned compiled program selects this source-bound RuleSpec parameter at the certified period.",
                }
            )
    for module, names in outputs.items():
        for name in names:
            rows.append(
                {
                    "source_surface": "engine_output",
                    "name": name,
                    "classification": "encoded",
                    "encoded_by": module,
                    "reason": "The pinned engine derives this value from the named RuleSpec module and the typed inputs below.",
                }
            )
    for name in (
        "best_start_family_scheme_income_for_relationship_period",
        "wff_family_scheme_income_for_relationship_period",
    ):
        rows.append(
            {
                "source_surface": "composition_output",
                "name": name,
                "classification": "encoded",
                "encoded_by": "nz-lane/emtr_reproduction/composition.yaml",
                "reason": "The pinned ops composition encodes this pass-through from family_scheme_income; it is not a supplied leaf.",
            }
        )
    rows.sort(key=lambda row: (row["source_surface"], row["name"]))
    if len(rows) != 35:
        raise ClosureError("NZ encoded host dependency inventory drifted from 35 rows")
    return rows


def _encoded_grounding_specs() -> dict[str, dict[str, dict[str, str]]]:
    """Request inputs that the pinned host derives from encoded module output."""

    return {
        "engine_request": {
            "independent_earner_tax_credit_receives_main_benefit": {
                "encoded_by": "nz/statutes/social_security/main_benefits/rates.yaml",
                "reason": (
                    "The pinned host wires this gate from the encoded weekly main-benefit "
                    "payment output (positive payment), rather than accepting a case leaf."
                ),
            },
            "in_work_tax_credit_person_or_partner_receives_main_benefit": {
                "encoded_by": "nz/statutes/social_security/main_benefits/rates.yaml",
                "reason": (
                    "The pinned host wires this gate from the encoded net main-benefit "
                    "output (positive payment), rather than accepting a case leaf."
                ),
            },
        }
    }


def _grouped_law_specs(
    groups: list[dict[str, Any]], *, label: str
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for group in groups:
        spec = {
            field: str(group[field])
            for field in ("derivation_instrument", "target_module", "size_class")
        }
        for name in group["names"]:
            if name in result:
                raise ClosureError(f"duplicate {label} law-derived input {name}")
            result[str(name)] = spec
    return result


def _scenario_declared_values(source_comparison: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, dict[str, Any]] = {}
    for scenario in source_comparison.get("scenarios") or []:
        inputs = scenario.get("inputs") if isinstance(scenario, Mapping) else None
        if not isinstance(inputs, Mapping):
            raise ClosureError("NZ scenario inputs are malformed")
        for name, value in inputs.items():
            values.setdefault(str(name), {})[_canonical_json(value)] = value
        for value in scenario.get("sampled_weekly_wages") or []:
            values.setdefault("sampled_weekly_wage1", {})[_canonical_json(value)] = (
                value
            )
    return {
        name: next(iter(distinct.values()))
        if len(distinct) == 1
        else [distinct[key] for key in sorted(distinct)]
        for name, distinct in sorted(values.items())
    }


def bootstrap_dependency_dispositions(
    source_comparison: Mapping[str, Any],
) -> dict[str, Any]:
    """Render the audited v3 dependency decisions from the pinned surfaces."""

    expected = _expected_dependency_inputs(source_comparison)
    law_by_surface = {
        "engine_request": _grouped_law_specs(
            _engine_law_groups(), label="engine-request"
        ),
        "implicit_legal_surface": _grouped_law_specs(
            _latent_law_groups(), label="implicit-surface"
        ),
        "eligibility_closure": _grouped_law_specs(
            _closure_law_groups(), label="eligibility-closure"
        ),
        "scenario": _grouped_law_specs(_scenario_law_groups(), label="scenario"),
    }
    world_by_surface = {
        "engine_request": _engine_world_reasons(),
        "implicit_legal_surface": _latent_world_reasons(),
        "eligibility_closure": _closure_world_reasons(),
        "scenario": _scenario_world_reasons(),
    }
    encoded_by_surface = _encoded_grounding_specs()
    scenario_values = _scenario_declared_values(source_comparison)
    rows: list[dict[str, Any]] = []
    for (surface, name), expected_fields in sorted(expected.items()):
        row: dict[str, Any] = {
            "source_surface": surface,
            "name": name,
            **{
                field: value
                for field, value in expected_fields.items()
                if field != "target_module"
            },
        }
        law_spec = law_by_surface.get(surface, {}).get(name)
        world_reason = world_by_surface.get(surface, {}).get(name)
        encoded_spec = encoded_by_surface.get(surface, {}).get(name)
        if surface == "host_rule":
            law_spec = {
                "derivation_instrument": (
                    "Income Tax Act 2007 ss MD 4, MD 8–MD 9 and MA 7 IWTC "
                    "entitlement, benefit, and earner gates; the Treasury "
                    "IncomeExplorer FamilyAssistance_IWTC_IncomeThreshold raw-"
                    "branch proxy has no identified statutory threshold equivalent"
                ),
                "target_module": (
                    "nz/statutes/income_tax/family_scheme/tax_credits.yaml"
                ),
                "size_class": "L",
            }
        if (
            sum(value is not None for value in (law_spec, world_reason, encoded_spec))
            != 1
        ):
            raise ClosureError(
                f"{surface}:{name}: audit must assign exactly one encoded, legal, or world grounding"
            )
        if encoded_spec is not None:
            row.update(
                {
                    "classification": "encoded",
                    **encoded_spec,
                }
            )
        elif law_spec is not None:
            expected_module = expected_fields.get("target_module")
            if (
                expected_module is not None
                and expected_module != law_spec["target_module"]
                and law_spec["target_module"] != "nz/policies/common/demographics.yaml"
            ):
                raise ClosureError(f"{surface}:{name}: audited target module drifted")
            row.update(
                {
                    "classification": "law_derived",
                    "leaf_kind": "law_derived",
                    **law_spec,
                    "reason": {
                        "engine_request": (
                            "The harness supplies or defaults a quantity whose defining instrument prescribes its legal derivation; case supply cannot close it under CERTIFIED.md v3."
                        ),
                        "implicit_legal_surface": (
                            "The host queries a rate-only output and bypasses this legally upstream eligibility or payability gate; omission from the request does not remove the dependency."
                        ),
                        "eligibility_closure": (
                            "The declared stylised choice is a legal conclusion, not an independently observable act; its defining rule must be encoded."
                        ),
                        "scenario": (
                            "The scenario label requires a statutory classification or calculation from observable records and therefore is not a permissible world-fact leaf."
                        ),
                        "host_rule": (
                            "The Treasury 1226.7 / 52.2 raw-branch shortcut is a "
                            "model proxy, not a statutory threshold; it must be "
                            "replaced by the encoded MD 4/MD 8–MD 9/MA 7 gates or "
                            "separately justified as a non-legal oracle convention."
                        ),
                    }[surface],
                }
            )
        else:
            row.update(
                {
                    "classification": "world_fact",
                    "leaf_kind": "world_fact",
                    "reason": world_reason,
                }
            )
        if surface == "scenario":
            row["declared_value"] = scenario_values[name]
        rows.append(row)
    law_count = sum(row["classification"] == "law_derived" for row in rows)
    world_count = sum(row["classification"] == "world_fact" for row in rows)
    encoded_count = sum(row["classification"] == "encoded" for row in rows)
    if (len(rows), law_count, world_count, encoded_count) != (288, 229, 57, 2):
        raise ClosureError("NZ dependency audit drifted from 288 / 229 / 57 / 2")
    return {
        "schema": "axiom_oracles.nz_dependency_dispositions.v1",
        "scope_receipts": _dependency_scope_receipts(),
        "encoded_dependencies": _encoded_dependency_inventory(),
        "input_grounding": rows,
    }


def _canonical_dependency_grounding(
    dispositions: Mapping[str, Any],
    source_comparison: Mapping[str, Any],
    *,
    rulespec_paths: set[str],
) -> list[dict[str, Any]]:
    expected = _expected_dependency_inputs(source_comparison)
    expected_receipts = _dependency_scope_receipts()
    if dispositions.get("scope_receipts") != expected_receipts:
        raise ClosureError("NZ dependency scope receipts drifted")
    canonical = bootstrap_dependency_dispositions(source_comparison)
    if dispositions.get("encoded_dependencies") != canonical["encoded_dependencies"]:
        raise ClosureError("NZ encoded dependency inventory drifted")

    rows = dispositions.get("input_grounding") or []
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    sort_keys: list[tuple[str, str]] = []
    common = {"source_surface", "name", "classification", "reason"}
    optional = {
        "canonical_request_name",
        "declared_value",
        "derivation_instrument",
        "encoded_by",
        "leaf_kind",
        "observed_state",
        "size_class",
        "target_module",
    }
    for index, value in enumerate(rows):
        if (
            not isinstance(value, dict)
            or set(value) - (common | optional)
            or not common.issubset(value)
        ):
            raise ClosureError(
                f"NZ dependency grounding row {index} has unexpected or missing keys"
            )
        surface, name = value.get("source_surface"), value.get("name")
        if not isinstance(surface, str) or not isinstance(name, str):
            raise ClosureError(f"NZ dependency grounding row {index} lacks names")
        key = (surface, name)
        if key not in expected:
            raise ClosureError(f"unknown NZ dependency input {surface}:{name}")
        if key in by_key:
            raise ClosureError(f"duplicate NZ dependency input {surface}:{name}")
        if not isinstance(value.get("reason"), str) or not value["reason"].strip():
            raise ClosureError(f"{surface}:{name}: grounding reason is empty")
        expected_fields = expected[key]
        for field, expected_value in expected_fields.items():
            if field == "target_module":
                continue
            if value.get(field) != expected_value:
                raise ClosureError(f"{surface}:{name}: {field} drifted")
        classification = value.get("classification")
        if classification == "encoded":
            if set(value) & {"leaf_kind", "derivation_instrument", "size_class"}:
                raise ClosureError(
                    f"{surface}:{name}: encoded input carries leaf fields"
                )
            if (
                not isinstance(value.get("encoded_by"), str)
                or value["encoded_by"] not in rulespec_paths
            ):
                raise ClosureError(f"{surface}:{name}: encoded_by is invalid")
        elif classification in {"world_fact", "law_derived"}:
            if value.get("leaf_kind") != classification:
                raise ClosureError(
                    f"{surface}:{name}: leaf_kind disagrees with classification"
                )
            if "encoded_by" in value:
                raise ClosureError(f"{surface}:{name}: a leaf may not carry encoded_by")
            if classification == "law_derived":
                for field in ("derivation_instrument", "target_module", "size_class"):
                    if (
                        not isinstance(value.get(field), str)
                        or not value[field].strip()
                    ):
                        raise ClosureError(
                            f"{surface}:{name}: law-derived leaf requires {field}"
                        )
                if value["target_module"] not in rulespec_paths:
                    raise ClosureError(f"{surface}:{name}: target_module is not pinned")
                if value["size_class"] not in {"S", "M", "L"}:
                    raise ClosureError(f"{surface}:{name}: invalid size_class")
            elif set(value) & {"derivation_instrument", "size_class", "target_module"}:
                raise ClosureError(
                    f"{surface}:{name}: world fact carries legal work fields"
                )
        else:
            raise ClosureError(f"{surface}:{name}: invalid dependency classification")
        by_key[key] = value
        sort_keys.append(key)
    if sort_keys != sorted(sort_keys):
        raise ClosureError("NZ dependency grounding rows are not canonically sorted")
    missing = sorted(set(expected) - set(by_key))
    if missing:
        surface, name = missing[0]
        raise ClosureError(f"missing NZ dependency grounding {surface}:{name}")
    if rows != canonical["input_grounding"]:
        raise ClosureError(
            "NZ dependency classifications or legal bindings drifted from the audited producer"
        )
    return rows


def _engine_law_groups() -> list[dict[str, Any]]:
    """Audited Part-1 groups; names partition the 131 legal request leaves."""

    return [
        {
            "names": ["acc_earnings_for_earners_levy"],
            "derivation_instrument": "Accident Compensation Act 2001 ss 6, 9–15, 221; Income Tax Act 2007 ss YA 1, RD 3B–3C; Accident Compensation (Earners' Levy) Regulations 2025 regs 4, 5, 8",
            "target_module": "nz/regulations/acc/earners_levy.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "independent_earner_tax_credit_entitled_to_or_receives_wff_tax_credit",
                "independent_earner_tax_credit_partner_entitled_to_and_receives_wff_tax_credit",
                "independent_earner_tax_credit_partner_receives_overseas_like_wff_tax_credit",
                "independent_earner_tax_credit_receives_overseas_like_support",
                "independent_earner_tax_credit_resident_in_new_zealand",
            ],
            "derivation_instrument": "Income Tax Act 2007 s LC 13(1)(d)–(h), including residence under ss YD 1 and HR 8",
            "target_module": "nz/statutes/income_tax/credits/individual_credits.yaml",
            "size_class": "L",
        },
        {
            "names": ["independent_earner_tax_credit_net_income"],
            "derivation_instrument": "Income Tax Act 2007 ss LC 13(4)–(5), BC 4–BC 5, BD 1",
            "target_module": "nz/statutes/income_tax/credits/individual_credits.yaml",
            "size_class": "L",
        },
        {
            "names": ["independent_earner_tax_credit_period_whole_months"],
            "derivation_instrument": "Income Tax Act 2007 s LC 13(2), (6) qualifying credit-period month cadence",
            "target_module": "nz/statutes/income_tax/credits/individual_credits.yaml",
            "size_class": "S",
        },
        {
            "names": [
                "in_work_tax_credit_child_exclusive_care_fraction",
                "wff_care_is_temporary",
                "wff_caregiver_is_disqualifying_residence_or_institution_operator_or_employee",
                "wff_caregiver_is_spouse_or_partner_of_non_electing_transitional_resident",
                "wff_caregiver_lives_apart_from_another_qualifying_person_for_child",
                "wff_commissioner_considers_primary_day_to_day_care",
            ],
            "derivation_instrument": "Income Tax Act 2007 s MC 10 principal-caregiver and care-allocation mechanics",
            "target_module": "nz/statutes/income_tax/family_scheme/eligibility.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "in_work_tax_credit_child_financially_dependent",
                "in_work_tax_credit_child_treated_financially_dependent_by_payments",
            ],
            "derivation_instrument": "Income Tax Act 2007 s MD 6 financially-dependent-child test",
            "target_module": "nz/statutes/income_tax/family_scheme/eligibility.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "in_work_tax_credit_child_new_zealand_resident",
                "in_work_tax_credit_child_present_in_new_zealand_for_entitlement_period",
                "in_work_tax_credit_person_new_zealand_resident",
                "in_work_tax_credit_person_present_in_new_zealand_continuous_months",
                "in_work_tax_credit_person_resident_under_yd1_on_credit_days",
                "in_work_tax_credit_person_spouse_or_partner_transitional_resident",
                "in_work_tax_credit_person_transitional_resident",
            ],
            "derivation_instrument": "Income Tax Act 2007 ss MD 7, YD 1, HR 8 residence and transitional-residence tests",
            "target_module": "nz/statutes/income_tax/family_scheme/eligibility.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "in_work_tax_credit_allowed_paye_income_payment",
                "in_work_tax_credit_birth_absence_weeks",
                "in_work_tax_credit_business_income_from_profit_activity",
                "in_work_tax_credit_close_company_derives_gross_income",
                "in_work_tax_credit_currently_meets_fifth_requirement",
                "in_work_tax_credit_days_since_last_met_fifth_requirement",
                "in_work_tax_credit_earner_in_relation_to_close_company",
                "in_work_tax_credit_earner_major_shareholder_in_close_company",
                "in_work_tax_credit_entitled_to_parental_tax_credit_for_child",
                "in_work_tax_credit_full_time_earner_income_at_incapacity",
                "in_work_tax_credit_normally_earner",
                "in_work_tax_credit_normally_full_time_earner",
                "in_work_tax_credit_personal_service_rehabilitation_payment_income",
                "in_work_tax_credit_rd3b_or_rd3c_income",
                "in_work_tax_credit_would_have_been_eligible_under_legacy_formula",
            ],
            "derivation_instrument": "Income Tax Act 2007 ss MD 9, MA 7, RD 3B–RD 3C and imported income/entity definitions",
            "target_module": "nz/statutes/income_tax/family_scheme/eligibility.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "family_scheme_base_income_excluding_mb3_to_mb13_adjustments",
                "family_scheme_retirement_scheme_distribution_income",
                "family_scheme_superannuation_distribution_income",
            ],
            "derivation_instrument": "Income Tax Act 2007 ss MB 1, BC, BD base-income rules",
            "target_module": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "family_scheme_activity_deductions",
                "family_scheme_activity_income",
            ],
            "derivation_instrument": "Income Tax Act 2007 s MB 3 activity-income calculation",
            "target_module": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "family_scheme_close_company_dependent_child_voting_interest",
                "family_scheme_close_company_dividends",
                "family_scheme_close_company_main_income_equalisation_deposits",
                "family_scheme_close_company_main_income_equalisation_refunds",
                "family_scheme_close_company_net_income",
                "family_scheme_close_company_person_voting_interest",
                "family_scheme_close_company_relevant_major_shareholders",
            ],
            "derivation_instrument": "Income Tax Act 2007 s MB 4 close-company attribution calculation",
            "target_module": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "family_scheme_trust_settlors_alive_count",
                "family_scheme_trustee_beneficiary_income_vested_or_paid",
                "family_scheme_trustee_company_dividends",
                "family_scheme_trustee_company_main_income_equalisation_deposits",
                "family_scheme_trustee_company_main_income_equalisation_refunds",
                "family_scheme_trustee_company_net_income",
                "family_scheme_trustee_company_voting_interest",
                "family_scheme_trustee_main_income_equalisation_deposits",
                "family_scheme_trustee_main_income_equalisation_refunds",
                "family_scheme_trustee_net_income",
            ],
            "derivation_instrument": "Income Tax Act 2007 s MB 7 settlor-trust and trustee/company attribution calculation",
            "target_module": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "family_scheme_employment_income_foregone_for_motor_vehicle",
                "family_scheme_short_term_charge_facility_value_excluding_fbt",
                "family_scheme_short_term_charge_facility_value_including_fbt",
            ],
            "derivation_instrument": "Income Tax Act 2007 s MB 7B employee benefit and short-term charge-facility calculation",
            "target_module": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "family_scheme_attributed_fringe_benefits_fbt_liability",
                "family_scheme_attributed_fringe_benefits_taxable_value",
                "family_scheme_controlling_shareholder_voting_interest",
            ],
            "derivation_instrument": "Income Tax Act 2007 s MB 8 controlling-shareholder fringe-benefit calculation",
            "target_module": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
            "size_class": "M",
        },
        {
            "names": ["family_scheme_exempt_pension_or_annuity_amount"],
            "derivation_instrument": "Income Tax Act 2007 s MB 10 pension/annuity inclusion",
            "target_module": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
            "size_class": "S",
        },
        {
            "names": [
                "family_scheme_dependent_child_principal_caregivers_count",
                "family_scheme_dependent_child_relevant_amounts",
            ],
            "derivation_instrument": "Income Tax Act 2007 s MB 11 dependent-child income calculation",
            "target_module": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "family_scheme_spouse_or_partner_nonresident_foreign_sourced_income"
            ],
            "derivation_instrument": "Income Tax Act 2007 s MB 12 non-resident partner income calculation",
            "target_module": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
            "size_class": "M",
        },
        {
            "names": ["family_scheme_non_settlor_trust_payment"],
            "derivation_instrument": "Income Tax Act 2007 s MB 12B non-settlor trust-payment calculation",
            "target_module": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
            "size_class": "M",
        },
        {
            "names": ["family_scheme_other_payments_not_excluded"],
            "derivation_instrument": "Income Tax Act 2007 s MB 13 replacement/living-expense payment classification; Tax Administration Act 1994 s 91AAS and the applicable emergency-event determinations",
            "target_module": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "family_tax_credit_eldest_dependent_child_care_units",
                "family_tax_credit_entitlement_days",
                "family_tax_credit_subsequent_dependent_child_care_units",
            ],
            "derivation_instrument": "Income Tax Act 2007 s MD 3 care-unit and entitlement-day mechanics",
            "target_module": "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "in_work_tax_credit_allowed_children_count",
                "in_work_tax_credit_weekly_periods",
            ],
            "derivation_instrument": "Income Tax Act 2007 ss MD 10 and ME 1 relevant-child and cadence mechanics",
            "target_module": "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "child_tax_credit_for_entitlement_period",
                "parental_tax_credit_additional_abatement",
                "parental_tax_credit_for_entitlement_period",
            ],
            "derivation_instrument": "Income Tax Act 2007 ss MZ 1–MZ 2 child-tax-credit entitlement/calculation and ss MD 11, MD 12, MD 12B, MD 16 parental-tax-credit entitlement/calculation/additional abatement",
            "target_module": "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            "size_class": "M",
        },
        {
            "names": ["wff_family_credit_abatement_days"],
            "derivation_instrument": "Income Tax Act 2007 s MD 13 abatement-day calculation",
            "target_module": "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            "size_class": "S",
        },
        {
            "names": [
                "minimum_family_adjusted_income_tax_liability",
                "minimum_family_full_time_earner_weeks",
                "minimum_family_scheme_income_attributable_to_full_time_weeks",
                "minimum_family_tax_credit_weekly_periods",
            ],
            "derivation_instrument": "Income Tax Act 2007 ss MA 7, ME 1–ME 3 MFTC eligibility, full-time-week and adjusted-income calculation",
            "target_module": "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "best_start_abatement_days",
                "best_start_child_care_fraction",
                "best_start_entitlement_days",
            ],
            "derivation_instrument": "Income Tax Act 2007 ss MG 2–MG 3 and MC 10 Best Start entitlement, care, and abatement mechanics",
            "target_module": "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            "size_class": "M",
        },
        {
            "names": ["taxable_income"],
            "derivation_instrument": "Income Tax Act 2007 ss BC 4–BC 5 and BD 1; Schedule 1 consumes but does not define taxable income",
            "target_module": "nz/statutes/income_tax/schedule_1/individual_income_tax.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "accommodation_supplement_boarder",
                "accommodation_supplement_costs_are_homeownership",
                "accommodation_supplement_owner_weekly_required_payments",
            ],
            "derivation_instrument": "Social Security Act 2018 s 65AAA boarder and qualifying accommodation-cost definitions",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "accommodation_supplement_additional_resident_in_social_housing",
                "accommodation_supplement_social_housing_weekly_contributions_paid",
            ],
            "derivation_instrument": "Public and Community Housing Management Act 1992 s 2 definitions of additional resident, applicable person, contributions, and social housing, imported by Social Security Act 2018 ss 65AAA–66",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "accommodation_supplement_has_dependent_children",
                "accommodation_supplement_has_two_or_more_dependent_children",
                "accommodation_supplement_in_relationship",
                "accommodation_supplement_sole_parent",
            ],
            "derivation_instrument": "Social Security Act 2018 s 8 definitions and Schedule 4 Part 7 household categories",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "M",
        },
        {
            "names": ["accommodation_supplement_base_rate_weekly_amount"],
            "derivation_instrument": "Social Security Act 2018 Schedule 4 Part 7 cls 1–6 and Social Security Regulations 2018 reg 17",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "accommodation_supplement_non_beneficiary",
                "accommodation_supplement_non_beneficiary_income_cutout_weekly_amount",
                "accommodation_supplement_relevant_weekly_income",
            ],
            "derivation_instrument": "Social Security Regulations 2018 regs 17–18 (especially reg 18(2A), (3)); Social Security Act 2018 Schedule 4 Part 1 cl 1 and Schedule 2 Income Tests 1 and 3 non-beneficiary base rate, relevant income, and cutout rules",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "accommodation_supplement_resides_in_area_1",
                "accommodation_supplement_resides_in_area_2",
                "accommodation_supplement_resides_in_area_3",
            ],
            "derivation_instrument": "Social Security Act 2018 Schedule 2 Accommodation Supplement area definitions, continued by Schedule 4 Part 7 cl 8 pending regulations under s 423",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "jobseeker_support_benefit_commenced_on_or_after_1998_07_01",
                "jobseeker_support_dependent_children_count",
                "jobseeker_support_single",
                "jobseeker_support_total_income",
                "jobseeker_support_youngest_dependent_child_age",
                "sole_parent_support_personal_earnings_used_for_childcare",
                "sole_parent_support_total_income",
            ],
            "derivation_instrument": "Social Security Act 2018 ss 7–8, 29–33, Schedule 2 income tests, Schedule 4 Part 1 cls 1, 3 and Part 2 cls 1–2",
            "target_module": "nz/statutes/social_security/main_benefits/rates.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "winter_energy_payment_has_dependent_children",
                "winter_energy_payment_single",
            ],
            "derivation_instrument": "Social Security Act 2018 Schedule 4 Part 8 cl 1 WEP household categories",
            "target_module": "nz/statutes/social_security/winter_energy_payment/core.yaml",
            "size_class": "M",
        },
        {
            "names": ["family_scheme_income_period_days"],
            "derivation_instrument": "Income Tax Act 2007 s MB 2 income-year and part-year day-count construction",
            "target_module": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
            "size_class": "S",
        },
        {
            "names": [
                "in_work_tax_credit_incapacity_suffered_between_2006_01_01_and_2006_03_31"
            ],
            "derivation_instrument": "Income Tax Act 2007 s MD 9(4)(b), applying incapacity under Accident Compensation Act 2001 ss 6, 25–26, 103, 105 and the statutory date window",
            "target_module": "nz/statutes/income_tax/family_scheme/eligibility.yaml",
            "size_class": "L",
        },
        {
            "names": ["in_work_tax_credit_person_age"],
            "derivation_instrument": "Income Tax Act 2007 s MD 5 age gate, calculated from birth and entitlement dates",
            "target_module": "nz/policies/common/demographics.yaml",
            "size_class": "S",
        },
        {
            "names": ["jobseeker_support_applicant_age"],
            "derivation_instrument": "Social Security Act 2018 Schedule 4 Part 1 cl 1 rate age band, calculated from birth and payment dates",
            "target_module": "nz/policies/common/demographics.yaml",
            "size_class": "S",
        },
        {
            "names": ["jobseeker_support_living_with_parent"],
            "derivation_instrument": "Social Security Act 2018 Schedule 4 Part 1 cl 8 statutory living-with-parent rate classification",
            "target_module": "nz/statutes/social_security/main_benefits/rates.yaml",
            "size_class": "M",
        },
        {
            "names": ["jobseeker_support_partner_ineligible_due_to_sanction_or_strike"],
            "derivation_instrument": "Social Security Act 2018 Schedule 4 Part 1 cl 3 and ss 225–229, 234–238 partner sanction/strike rate classification",
            "target_module": "nz/statutes/social_security/main_benefits/rates.yaml",
            "size_class": "L",
        },
        {
            "names": ["jobseeker_support_partner_receives_main_benefit"],
            "derivation_instrument": "Social Security Act 2018 Schedule 4 Part 1 cl 1(g) partner-main-benefit rate classification; the current harness's partnered proxy is not a payment-register fact",
            "target_module": "nz/statutes/social_security/main_benefits/rates.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "accommodation_supplement_area_let_to_nonresidents",
                "accommodation_supplement_self_contained_area_let_to_residents",
            ],
            "derivation_instrument": "Social Security Act 2018 s 65AAA(a)–(e) statutory occupancy, ownership, business-use, and let-area classifications",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "accommodation_supplement_business_use_area",
                "accommodation_supplement_joint_owner_with_resident",
                "accommodation_supplement_owns_premises_and_not_joint_owner_with_resident",
            ],
            "derivation_instrument": "Social Security Act 2018 s 65AAA(a)–(e) statutory ownership and business-use classifications",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "S",
        },
        {
            "names": [
                "accommodation_supplement_weekly_boarder_payments_received",
                "accommodation_supplement_weekly_contributions_received_from_additional_residents",
                "accommodation_supplement_weekly_rent_received_from_other_residents",
            ],
            "derivation_instrument": "Social Security Act 2018 ss 65AAA, 66(c) and Schedule 4 Part 7 cl 7 statutory weekly cost, contribution, and receipt aggregations",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "accommodation_supplement_weekly_board_and_lodgings_paid",
                "accommodation_supplement_weekly_rent_paid",
            ],
            "derivation_instrument": "Social Security Act 2018 ss 65AAA, 66(c) and Schedule 4 Part 7 cl 7 statutory weekly qualifying-payment aggregations",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "S",
        },
    ]


def _engine_world_reasons() -> dict[str, str]:
    groups = [
        (
            {
                "independent_earner_tax_credit_person_is_natural_person",
                "wff_caregiver_is_body_of_persons",
            },
            "Person/entity identity is grounded only by a civil or entity register record; the stylised constant is not itself that record.",
        ),
        (
            {
                "independent_earner_tax_credit_receives_new_zealand_superannuation",
                "independent_earner_tax_credit_receives_veterans_pension",
                "in_work_tax_credit_person_or_partner_receives_basic_and_independent_circumstances_grants",
                "in_work_tax_credit_person_or_partner_receives_parent_allowance_or_childrens_pension",
                "in_work_tax_credit_child_tax_credit_received_for_period_ending_2006_03_31",
                "in_work_tax_credit_weekly_compensation_paid_for_incapacity",
                "minimum_family_amount_paid",
                "minimum_family_amount_received",
                "jobseeker_support_partner_receives_new_zealand_superannuation_or_veterans_pension",
            },
            "Actual receipt/payment history is an observable agency-register fact; the harness constant requires a bound IRD/MSD/ACC/Veterans' Affairs record in a real execution.",
        ),
        (
            {
                "in_work_tax_credit_work_reduced_or_stopped_due_to_child_birth",
            },
            "The dated incapacity, birth-related work event, strike, or issued sanction is independently observable from event and agency records.",
        ),
        (
            {"family_scheme_employee_salary_or_wages"},
            "Reported salary or wages on the scenario are payroll facts; their later legal classification is encoded or remains separately open.",
        ),
        (
            {"family_scheme_commissioner_excludes_non_settlor_trust_payment"},
            "Only an issued Commissioner decision or decision-register entry is a world fact; the harness's false constant currently lacks that receipt.",
        ),
        (
            {
                "accommodation_supplement_total_premises_area",
            },
            "Measured premises area and the documented use/occupancy arrangement are independently observable property facts.",
        ),
        (
            {
                "accommodation_supplement_owner_weekly_payment_share",
            },
            "The raw paid/received amount or issued MSD payment-share determination is an observable contract/payment record.",
        ),
        (
            {
                "jobseeker_support_transferred_2013_no_dependent_children",
            },
            "Household residence and the historical MSD award/migration entry are observable case/register facts.",
        ),
    ]
    result: dict[str, str] = {}
    for names, reason in groups:
        for name in names:
            if name in result:
                raise ClosureError(f"duplicate audited engine world fact {name}")
            result[name] = reason
    return result


def _latent_law_groups() -> list[dict[str, Any]]:
    return [
        {
            "names": [
                "social_security_continuous_residence_years_after_citizen_or_resident",
                "social_security_continuous_residence_years_before_application",
                "social_security_ordinarily_resident_in_new_zealand_on_application",
                "social_security_ordinarily_resident_in_reciprocity_country",
                "social_security_regulations_treat_person_as_meeting_residence_requirement",
                "social_security_section_205_override_applies",
                "social_security_unlawfully_resident_or_present_in_new_zealand",
            ],
            "derivation_instrument": "Social Security Act 2018 ss 16, 19, 205 residential/lawful-presence and reciprocity rules; Social Security Regulations 2018 regs 6, 7, 7A absence-return, overseas-PAYE-residence, and response-visa deeming rules",
            "target_module": "nz/statutes/social_security/main_benefits/entitlement.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "jobseeker_available_for_and_seeking_full_time_employment",
                "jobseeker_has_dependent_child",
                "jobseeker_has_no_income",
                "jobseeker_health_condition_injury_or_disability_limits_capacity_to_seek_or_undertake_work",
                "jobseeker_in_full_time_employment",
                "jobseeker_income_less_than_zero_rate_cutout",
                "jobseeker_losing_earnings_through_health_condition_or_injury",
                "jobseeker_taken_reasonable_steps_to_find_full_time_employment",
                "jobseeker_temporary_income_reduces_rate_to_zero_but_otherwise_entitled",
                "jobseeker_willing_and_able_to_undertake_full_time_employment",
                "jobseeker_would_satisfy_available_for_work_but_for_work_test_exemption_circumstances",
            ],
            "derivation_instrument": "Social Security Act 2018 ss 20–26 Jobseeker Support availability, work-test, capacity, income and zero-rate entitlement rules",
            "target_module": "nz/statutes/social_security/main_benefits/entitlement.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "sole_parent_caring_for_dependent_children_under_age_limit",
                "sole_parent_is_mother_or_father_or_child_regarded_as_child",
                "sole_parent_is_single",
                "sole_parent_living_apart_and_lost_or_lacks_partner_support",
                "sole_parent_lost_regular_support_due_to_partner_sentence_conditions",
                "sole_parent_split_care_situation_applies",
            ],
            "derivation_instrument": "Social Security Act 2018 ss 29–32 Sole Parent Support relationship, child, lost-support, and split-care tests",
            "target_module": "nz/statutes/social_security/main_benefits/entitlement.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "winter_energy_payment_absence_days_do_not_affect_section_72_eligibility",
                "winter_energy_payment_income_based_ltr_care_contribution_below_maximum",
                "winter_energy_payment_payment_would_be_payable_but_for_absence",
                "winter_energy_payment_qualifying_benefit_payable",
                "winter_energy_payment_rcdss_50_plus_single_person",
                "winter_energy_payment_rcdss_qualifying_person",
            ],
            "derivation_instrument": "Social Security Act 2018 ss 71–72, 220 WEP qualifying-benefit, residential-care, and absence rules",
            "target_module": "nz/statutes/social_security/winter_energy_payment/core.yaml",
            "size_class": "M",
        },
        {
            "names": ["winter_energy_payment_absence_days_during_winter_period"],
            "derivation_instrument": "Social Security Act 2018 s 220 statutory absence-window count from border dates",
            "target_module": "nz/statutes/social_security/winter_energy_payment/core.yaml",
            "size_class": "S",
        },
        {
            "names": [
                "accommodation_supplement_cash_assets",
                "accommodation_supplement_has_accommodation_costs",
                "accommodation_supplement_receiving_or_eligible_for_student_allowance_grant",
                "accommodation_supplement_section_68_joint_tenant_exception_applies",
                "accommodation_supplement_super_or_veterans_pension_income_above_schedule_5_limit",
            ],
            "derivation_instrument": "Social Security Act 2018 ss 65–69, Schedule 5 and Social Security Regulations 2018 reg 15 Accommodation Supplement non-rate entitlement; Student Allowances Regulations 1998 regs 2–8, 12, 12A–16, 20, 26, 28–31, 34–35, 40, 44–46, 47B–47E, 48 student-allowance/basic-grant/independent-circumstances-grant eligibility gate",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "best_start_child_age_and_birth_date_requirement",
                "best_start_parental_tax_credit_for_child",
                "best_start_person_is_principal_caregiver_for_child",
                "parental_tax_credit_child_exclusive_care_fraction",
                "wff_child_exclusive_care_fraction_for_family_or_best_start_credit",
                "wff_child_new_zealand_resident",
                "wff_child_present_in_new_zealand_for_entitlement_period",
                "wff_credit_child_financially_independent",
                "wff_dependent_child_status_stopped_except_first_or_last_day",
                "wff_dependent_children_principal_caregiver_count",
                "wff_meets_qualifying_criteria_each_day",
                "wff_person_entitled_to_emergency_benefit",
                "wff_person_new_zealand_resident",
                "wff_person_present_in_new_zealand_continuous_months",
                "wff_person_resident_under_yd1_on_credit_days",
                "wff_person_spouse_or_partner_transitional_resident",
                "wff_person_transitional_resident",
                "wff_principal_caregiver_status_changed_except_first_or_last_day",
                "wff_protected_family_tax_credit_status_changed_except_first_or_last_day",
                "wff_spouse_or_partner_combined_entitlement_applies",
                "wff_spouse_or_partner_started_or_stopped_during_entitlement_period",
                "wff_tax_credit_composition_changed_except_first_or_last_day",
            ],
            "derivation_instrument": "Income Tax Act 2007 ss MC 2–MC 10 and MG 1 general WFF/Best Start eligibility, care, residence, relationship and change-day rules",
            "target_module": "nz/statutes/income_tax/family_scheme/eligibility.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "accommodation_supplement_concessionary_mortgage_payments_to_kainga_ora_or_crown"
            ],
            "derivation_instrument": "Social Security Act 2018 s 65AAA concessionary-mortgage qualifying-cost classification",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "M",
        },
        {
            "names": ["jobseeker_applicant_age"],
            "derivation_instrument": "Social Security Act 2018 s 23 age eligibility, calculated from birth and application dates",
            "target_module": "nz/policies/common/demographics.yaml",
            "size_class": "S",
        },
        {
            "names": ["jobseeker_full_time_student"],
            "derivation_instrument": "Social Security Act 2018 Schedule 2 student definitions and ss 23–25; Student Allowances Regulations 1998 regs 2–8, 12, 12A–16, 20, 26, 28–31, 34–35, 40, 44–46, 47B–47E, 48 interpretation and operative allowance/grant eligibility provisions",
            "target_module": "nz/statutes/social_security/main_benefits/entitlement.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "jobseeker_unemployed_or_on_leave_for_employment_related_training"
            ],
            "derivation_instrument": "Social Security Act 2018 s 26(c) employment-related training and MSD reasonable-belief test",
            "target_module": "nz/statutes/social_security/main_benefits/entitlement.yaml",
            "size_class": "M",
        },
        {
            "names": ["jobseeker_unemployed_due_to_strike"],
            "derivation_instrument": "Social Security Act 2018 s 26(b) causal strike-participation and same-union/same-workplace unemployment test",
            "target_module": "nz/statutes/social_security/main_benefits/entitlement.yaml",
            "size_class": "M",
        },
        {
            "names": ["sole_parent_applicant_age"],
            "derivation_instrument": "Social Security Act 2018 s 29(d) age eligibility, calculated from birth and application dates",
            "target_module": "nz/policies/common/demographics.yaml",
            "size_class": "S",
        },
        {
            "names": ["sole_parent_split_care_court_order_exception_applies"],
            "derivation_instrument": "Social Security Act 2018 s 32(3) statutory court-order exception test",
            "target_module": "nz/statutes/social_security/main_benefits/entitlement.yaml",
            "size_class": "M",
        },
        {
            "names": ["wff_credit_child_age"],
            "derivation_instrument": "Income Tax Act 2007 s MC 9 dependent-child age test, calculated from birth and entitlement dates",
            "target_module": "nz/policies/common/demographics.yaml",
            "size_class": "S",
        },
        {
            "names": ["wff_person_age"],
            "derivation_instrument": "Income Tax Act 2007 s MC 3 claimant age test, calculated from birth and entitlement dates",
            "target_module": "nz/policies/common/demographics.yaml",
            "size_class": "S",
        },
        {
            "names": ["winter_energy_payment_person_age"],
            "derivation_instrument": "Social Security Act 2018 s 72(2)(c), (ca) age gate, calculated from birth and winter-period dates",
            "target_module": "nz/policies/common/demographics.yaml",
            "size_class": "S",
        },
        {
            "names": ["winter_energy_payment_valid_election_not_to_receive_in_force"],
            "derivation_instrument": "Social Security Act 2018 ss 72(2)(e), 73 validity, effect, and revocation of an election not to receive WEP",
            "target_module": "nz/statutes/social_security/winter_energy_payment/core.yaml",
            "size_class": "M",
        },
    ]


def _latent_world_reasons() -> dict[str, str]:
    groups = [
        (
            {
                "main_benefit_receiving_another_main_benefit",
                "main_benefit_receiving_new_zealand_superannuation",
                "main_benefit_receiving_veterans_pension",
                "winter_energy_payment_receiving_main_benefit",
                "winter_energy_payment_receiving_new_zealand_superannuation",
                "winter_energy_payment_receiving_veterans_pension",
                "wff_relationship_period_main_benefit_received",
                "wff_relationship_period_parent_allowance_or_childrens_pension_received",
                "best_start_parent_allowance_or_childrens_pension_for_child",
                "best_start_parental_leave_or_preterm_baby_payment_for_child_period",
            },
            "Actual benefit, pension, allowance, or parental-leave payment is grounded to the issuing agency's payment register.",
        ),
        (
            {
                "social_security_new_zealand_citizen",
                "social_security_only_temporary_entry_class_visa_holder",
                "social_security_refugee_or_protected_person",
                "social_security_residence_class_visa_holder",
            },
            "Citizenship, visa, refugee, or protected-person status is an observable immigration/register entry.",
        ),
        (
            {
                "wff_credit_child_attending_school_or_tertiary",
            },
            "Enrolment, training, or employment-leave status is grounded to school, tertiary, employer, or training records.",
        ),
        (
            {
                "jobseeker_section_25_discretionary_student_eligibility",
                "sole_parent_split_care_entitlement_allocated_to_person",
                "winter_energy_payment_partnered_rate_and_partner_determined_entitled",
            },
            "Only an issued MSD/IRD discretionary or allocation determination is a world fact; an unreceipted harness proxy is not.",
        ),
        (
            {
                "sole_parent_marriage_or_civil_union_dissolved",
                "sole_parent_spouse_or_partner_died",
            },
            "The strike event, dissolution judgment/register entry, court order, or death-register entry is an observable act.",
        ),
        (
            {
                "winter_energy_payment_absent_from_new_zealand",
                "winter_energy_payment_disability_or_chronic_condition_residential_care_partly_funded",
                "winter_energy_payment_qualifying_benefit_reduced_to_long_term_hospital_rate_and_payment_terminated_after_review",
                "winter_energy_payment_residential_care_cost_contribution_redirected_from_benefit",
            },
            "Border, care-funding, issued review/termination, payment-redirection, or filed-election records are observable acts.",
        ),
        (
            {
                "accommodation_supplement_disability_accommodation_or_care_funded_under_pae_ora_act",
                "accommodation_supplement_partner_receiving_accommodation_supplement",
                "accommodation_supplement_rent_paid_to_kainga_ora",
                "accommodation_supplement_rent_paid_to_registered_community_housing_provider_social_housing",
                "accommodation_supplement_residential_care_funded_under_residential_care_act",
            },
            "The raw payment, provider, partner-payment, or statutory care-funding register entry is independently observable.",
        ),
        (
            {"wff_spouse_or_partner_combined_entitlement_allocated_to_person"},
            "Only an issued IRD spouse/partner allocation is a world fact; no generic legal choice can substitute for the decision.",
        ),
    ]
    result: dict[str, str] = {}
    for names, reason in groups:
        for name in names:
            if name in result:
                raise ClosureError(f"duplicate audited latent world fact {name}")
            result[name] = reason
    return result


def _closure_law_groups() -> list[dict[str, Any]]:
    return [
        {
            "names": ["residence.wff_caregiver_disqualifying_status"],
            "derivation_instrument": "Income Tax Act 2007 s MC 10 caregiver disqualifications",
            "target_module": "nz/statutes/income_tax/family_scheme/eligibility.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "residence.iwtc_child_new_zealand_resident_when_present",
                "residence.iwtc_child_present_for_entitlement_period_when_present",
                "residence.iwtc_person_new_zealand_resident",
                "residence.iwtc_person_present_in_new_zealand_continuous_months",
                "residence.iwtc_person_resident_under_yd1_on_credit_days",
                "residence.iwtc_person_spouse_or_partner_transitional_resident",
                "residence.iwtc_person_transitional_resident",
            ],
            "derivation_instrument": "Income Tax Act 2007 ss MD 7, YD 1, HR 8 residence and transitional-residence tests",
            "target_module": "nz/statutes/income_tax/family_scheme/eligibility.yaml",
            "size_class": "L",
        },
        {
            "names": ["residence.ietc_person_resident_in_new_zealand"],
            "derivation_instrument": "Income Tax Act 2007 ss LC 13(1)(h), YD 1 residence test",
            "target_module": "nz/statutes/income_tax/credits/individual_credits.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "care.iwtc_child_exclusive_care_fraction",
                "care.wff_care_is_temporary",
                "care.wff_caregiver_lives_apart_when_child_present",
                "care.wff_commissioner_considers_primary_day_to_day_care_when_child_present",
            ],
            "derivation_instrument": "Income Tax Act 2007 s MC 10 principal-caregiver and care-allocation mechanics",
            "target_module": "nz/statutes/income_tax/family_scheme/eligibility.yaml",
            "size_class": "M",
        },
        {
            "names": ["care.best_start_child_care_fraction"],
            "derivation_instrument": "Income Tax Act 2007 ss MC 10 and MG 2(5) Best Start care fraction",
            "target_module": "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            "size_class": "M",
        },
        {
            "names": [
                "work_tests.iwtc_allowed_paye_income_payment_when_wages_positive",
                "work_tests.iwtc_currently_meets_fifth_requirement",
                "work_tests.iwtc_normally_earner_when_wages_positive",
            ],
            "derivation_instrument": "Income Tax Act 2007 s MD 9 qualifying-income, normal-earner, and fifth-requirement tests",
            "target_module": "nz/statutes/income_tax/family_scheme/eligibility.yaml",
            "size_class": "L",
        },
        {
            "names": [
                "work_tests.mftc_couple_full_time_hours_per_week",
                "work_tests.mftc_single_full_time_hours_per_week",
            ],
            "derivation_instrument": "Income Tax Act 2007 s MA 7(1)(a)–(b), (2) MFTC full-time-earner hours and modifications",
            "target_module": "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            "size_class": "L",
        },
        {
            "names": ["gates.iwtc_main_benefit_disqualifies"],
            "derivation_instrument": "Income Tax Act 2007 s MD 8 main-benefit gate",
            "target_module": "nz/statutes/income_tax/family_scheme/eligibility.yaml",
            "size_class": "S",
        },
        {
            "names": ["gates.ietc_main_benefit_disqualifies"],
            "derivation_instrument": "Income Tax Act 2007 s LC 13(1)(a) main-benefit gate",
            "target_module": "nz/statutes/income_tax/credits/individual_credits.yaml",
            "size_class": "S",
        },
        {
            "names": ["gates.ietc_wff_disqualifies"],
            "derivation_instrument": "Income Tax Act 2007 s LC 13(1)(d)–(e) WFF entitlement/receipt gate, as amended by 2025 No 9 s 105",
            "target_module": "nz/statutes/income_tax/credits/individual_credits.yaml",
            "size_class": "M",
        },
        {
            "names": ["gates.ietc_overseas_like_support_received"],
            "derivation_instrument": "Income Tax Act 2007 s LC 13(1)(f)–(g) overseas support 'in the nature of' classification",
            "target_module": "nz/statutes/income_tax/credits/individual_credits.yaml",
            "size_class": "M",
        },
    ]


def _closure_world_reasons() -> dict[str, str]:
    return {
        "gates.ietc_new_zealand_superannuation_received": "Actual New Zealand Superannuation receipt is an observable MSD payment-register fact; the false constant requires that receipt.",
        "gates.ietc_veterans_pension_received": "Actual Veterans' Pension receipt is an observable Veterans' Affairs/MSD payment-register fact; the false constant requires that receipt.",
        "gates.iwtc_basic_or_independent_grants_received": "Actual basic or independent-circumstances grant receipt is an observable agency payment-register fact.",
        "gates.iwtc_parent_allowance_or_childrens_pension_received": "Actual parent allowance or children's pension receipt is an observable agency payment-register fact.",
    }


def _scenario_law_groups() -> list[dict[str, Any]]:
    return [
        {
            "names": ["accommodation_area"],
            "derivation_instrument": "Social Security Act 2018 Schedule 2 Accommodation Supplement area definitions, continued by Schedule 4 Part 7 cl 8 pending regulations under s 423",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "M",
        },
        {
            "names": ["accommodation_boarder"],
            "derivation_instrument": "Social Security Act 2018 s 65AAA boarder definition",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "M",
        },
        {
            "names": ["accommodation_costs"],
            "derivation_instrument": "Social Security Act 2018 s 65AAA qualifying mortgage/rent cost inclusions, exclusions, and MSD-satisfaction mechanics",
            "target_module": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "size_class": "L",
        },
        {
            "names": ["partnered"],
            "derivation_instrument": "Social Security Act 2018 s 8 relationship definitions; Income Tax Act 2007 s YA 1 spouse, civil-union-partner, de-facto-partner, and partner definitions and s MA 7 family-scheme partner rule",
            "target_module": "nz/statutes/social_security/main_benefits/entitlement.yaml",
            "size_class": "M",
        },
        {
            "names": ["children_ages"],
            "derivation_instrument": (
                "Birth-register dates; Income Tax Act 2007 ss MC 2, MC 3, "
                "MC 6–MC 9; Social Security Act 2018 ss 23, 29, 72 and "
                "Schedule 2 dependent-child/young-person definitions"
            ),
            "target_module": "nz/policies/common/demographics.yaml",
            "size_class": "S",
        },
    ]


def _scenario_world_reasons() -> dict[str, str]:
    return {
        "accommodation_rent": "The title or tenancy arrangement is an observable documented contract/property fact.",
        "gross_wage2": "The partner's reported wage is an observable payroll/scenario amount.",
        "hours2": "The partner's worked hours are observable payroll/roster facts.",
        "sampled_weekly_wage1": "The sampled primary wage is the comparison's reported scenario amount.",
        "wage1_hourly": "The primary hourly wage is an observable payroll/contract amount.",
        "weekly_board_and_lodgings_paid": "The raw board/lodgings amount paid is an observable payment/contract record.",
    }


def _build_dependency_closure(
    grounding_rows: list[dict[str, Any]],
    instrument_decisions: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    law_derived_inputs = sorted(
        f"{row['source_surface']}:{row['name']}"
        for row in grounding_rows
        if row.get("leaf_kind") == "law_derived"
    )
    world_facts = sorted(
        f"{row['source_surface']}:{row['name']}"
        for row in grounding_rows
        if row.get("leaf_kind") == "world_fact"
    )
    encoded_inputs = sorted(
        f"{row['source_surface']}:{row['name']}"
        for row in grounding_rows
        if row.get("classification") == "encoded"
    )
    instruments_bearing = {
        str(row["eli"])
        for row in instrument_decisions.get("instrument_dispositions") or []
        if isinstance(row, Mapping)
        and row.get("status") == "pending"
        and row.get("bears_on_computed_surface") is True
        and isinstance(row.get("eli"), str)
    }
    instruments_bearing.update(
        str(row["eli"])
        for row in instrument_decisions.get("supplemental_instruments") or []
        if isinstance(row, Mapping)
        and row.get("status") == "pending"
        and row.get("bears_on_computed_surface") is True
        and isinstance(row.get("eli"), str)
    )
    bearing = sorted(instruments_bearing)
    open_count = len(law_derived_inputs) + len(bearing)
    return (
        {
            "law_derived_inputs": law_derived_inputs,
            "instruments_bearing_on_computed": bearing,
            "open_dependency_count": open_count,
            "closed": open_count == 0,
        },
        {
            "input_count": len(grounding_rows),
            "counts": {
                "encoded": len(encoded_inputs),
                "world_fact": len(world_facts),
                "law_derived": len(law_derived_inputs),
            },
            "complete": (
                len(encoded_inputs) + len(world_facts) + len(law_derived_inputs)
                == len(grounding_rows)
            ),
            "encoded_inputs": encoded_inputs,
            "world_facts": world_facts,
            "law_derived_inputs": law_derived_inputs,
            "ledger": grounding_rows,
        },
    )


def _expected_instrument_pairs(graph: Mapping[str, Any]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for row in graph.get("instruments") or []:
        if not isinstance(row, Mapping):
            continue
        act = INSTRUMENT_ACTS[str(row["act_citation_path"])]
        for program in act["programs"]:
            pairs.add((str(program), str(row["eli"])))
    return pairs


def _canonical_instrument_decisions(
    graph: Mapping[str, Any],
    decisions: Mapping[str, Any],
    *,
    rulespec_paths: set[str],
) -> dict[tuple[str, str], dict[str, Any]]:
    expected = _expected_instrument_pairs(graph)
    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    sort_keys: list[tuple[str, str]] = []
    for index, value in enumerate(decisions.get("instrument_dispositions") or []):
        if not isinstance(value, dict):
            raise ClosureError(f"instrument disposition row {index} is not an object")
        allowed = {"program", "eli", "status"} | _DISPOSITION_OPTIONAL
        if not {"program", "eli", "status"}.issubset(value) or not set(value).issubset(
            allowed
        ):
            raise ClosureError(
                f"instrument disposition row {index} has unexpected or missing keys"
            )
        if not isinstance(value["program"], str) or not isinstance(value["eli"], str):
            raise ClosureError(
                f"instrument disposition row {index} program/eli must be strings"
            )
        pair = (value["program"], value["eli"])
        if pair not in expected:
            raise ClosureError(
                f"unknown NZ instrument disposition {pair[0]} / {pair[1]}"
            )
        if pair in by_pair:
            raise ClosureError(
                f"duplicate NZ instrument disposition {pair[0]} / {pair[1]}"
            )
        status = value.get("status")
        if status not in INSTRUMENT_STATUSES:
            raise ClosureError(f"{pair[0]} / {pair[1]}: invalid disposition status")
        if status == "pending":
            unexpected = {"classification", "encoded_by"} & set(value)
            if unexpected:
                raise ClosureError(
                    f"{pair[0]} / {pair[1]}: pending disposition must not carry "
                    "classification or encoded_by"
                )
            bearing = value.get("bears_on_computed_surface")
            if bearing is not None and not isinstance(bearing, bool):
                raise ClosureError(
                    f"{pair[0]} / {pair[1]}: bears_on_computed_surface must be boolean"
                )
            if bearing is True:
                for field in (
                    "reason",
                    "bearing",
                    "defining_provision",
                    "target_module",
                    "size_class",
                ):
                    if (
                        not isinstance(value.get(field), str)
                        or not value[field].strip()
                    ):
                        raise ClosureError(
                            f"{pair[0]} / {pair[1]}: bearing pending row requires {field}"
                        )
                if value["size_class"] not in {"S", "M", "L"}:
                    raise ClosureError(f"{pair[0]} / {pair[1]}: invalid size_class")
            elif _DISPOSITION_OPTIONAL & set(value):
                raise ClosureError(
                    f"{pair[0]} / {pair[1]}: ordinary pending row must not carry disposition metadata"
                )
        else:
            for field in ("classification", "reason"):
                if not isinstance(value.get(field), str) or not value[field].strip():
                    raise ClosureError(
                        f"{pair[0]} / {pair[1]}: {status} requires {field}"
                    )
            if status == "encoded" and (
                not isinstance(value.get("encoded_by"), str)
                or not value["encoded_by"].strip()
            ):
                raise ClosureError(
                    f"{pair[0]} / {pair[1]}: encoded requires encoded_by"
                )
            if status == "encoded" and value["encoded_by"] not in rulespec_paths:
                raise ClosureError(
                    f"{pair[0]} / {pair[1]}: encoded_by is not a pinned RuleSpec module"
                )
            if status != "encoded" and "encoded_by" in value:
                raise ClosureError(
                    f"{pair[0]} / {pair[1]}: only encoded may carry encoded_by"
                )
            if "bearing" in value and (
                not isinstance(value["bearing"], str) or not value["bearing"].strip()
            ):
                raise ClosureError(
                    f"{pair[0]} / {pair[1]}: bearing must be a non-empty string"
                )
            bears = value.get("bears_on_computed_surface")
            if not isinstance(bears, bool):
                raise ClosureError(
                    f"{pair[0]} / {pair[1]}: {status} requires boolean bears_on_computed_surface"
                )
            if status in {"classified-with-reason", "excluded-with-reason"} and bears:
                raise ClosureError(
                    f"{pair[0]} / {pair[1]}: an instrument bearing on a computed surface must be encoded or pending"
                )
        by_pair[pair] = value
        sort_keys.append(pair)
    if sort_keys != sorted(sort_keys):
        raise ClosureError("NZ instrument dispositions are not canonically sorted")
    missing = sorted(expected - set(by_pair))
    if missing:
        program, eli = missing[0]
        raise ClosureError(f"missing NZ instrument disposition {program} / {eli}")
    return by_pair


def _canonical_supplemental_instruments(
    graph: Mapping[str, Any],
    decisions: Mapping[str, Any],
    *,
    rulespec_paths: set[str],
) -> list[dict[str, Any]]:
    """Validate subject-search/citation-scan additions outside the PCO graph."""

    graph_elis = {
        str(row["eli"])
        for row in graph.get("instruments") or []
        if isinstance(row, Mapping) and isinstance(row.get("eli"), str)
    }
    allowed_programs = set(PROGRAM_INSTRUMENT_ACT)
    required = {
        "eli",
        "title_short",
        "programs",
        "status",
        "provenance",
        "discovery_channels",
        "bears_on_computed_surface",
        "reason",
    }
    optional = {
        "bearing",
        "defining_provision",
        "encoded_by",
        "size_class",
        "target_module",
    }
    rows: list[dict[str, Any]] = []
    keys: list[str] = []
    for index, value in enumerate(decisions.get("supplemental_instruments") or []):
        if (
            not isinstance(value, dict)
            or not required.issubset(value)
            or not set(value).issubset(required | optional)
        ):
            raise ClosureError(
                f"supplemental instrument row {index} has unexpected or missing keys"
            )
        eli = value.get("eli")
        if not isinstance(eli, str) or not eli:
            raise ClosureError(f"supplemental instrument row {index} has invalid eli")
        if eli in graph_elis:
            raise ClosureError(f"supplemental instrument duplicates graph ELI {eli}")
        programs = value.get("programs")
        if (
            not isinstance(programs, list)
            or programs != sorted(set(programs))
            or not programs
            or not set(programs).issubset(allowed_programs)
        ):
            raise ClosureError(f"{eli}: invalid supplemental program set")
        channels = value.get("discovery_channels")
        if (
            not isinstance(channels, list)
            or channels != sorted(set(channels))
            or not channels
            or not all(isinstance(channel, str) and channel for channel in channels)
            or not set(channels).issubset(
                {"subject_matter_search", "corpus_citation_scan_approximation"}
            )
        ):
            raise ClosureError(f"{eli}: invalid discovery channels")
        for field in ("title_short", "provenance", "reason"):
            if not isinstance(value.get(field), str) or not value[field].strip():
                raise ClosureError(f"{eli}: supplemental row requires {field}")
        status = value.get("status")
        if status not in {"encoded", "excluded-with-reason", "pending"}:
            raise ClosureError(f"{eli}: invalid supplemental disposition")
        if status == "encoded":
            if value.get("bears_on_computed_surface") is not True:
                raise ClosureError(f"{eli}: encoded supplement must declare bearing")
            encoded_by = value.get("encoded_by")
            if (
                not isinstance(encoded_by, list)
                or encoded_by != sorted(set(encoded_by))
                or not encoded_by
                or not set(encoded_by).issubset(rulespec_paths)
            ):
                raise ClosureError(f"{eli}: encoded supplement has invalid encoded_by")
            for field in (
                "bearing",
                "defining_provision",
                "size_class",
                "target_module",
            ):
                if field in value:
                    raise ClosureError(
                        f"{eli}: encoded supplemental row must not carry open-work field {field}"
                    )
        elif status == "pending":
            if value.get("bears_on_computed_surface") is not True:
                raise ClosureError(f"{eli}: pending supplement must declare bearing")
            if "encoded_by" in value:
                raise ClosureError(
                    f"{eli}: pending supplement may not carry encoded_by"
                )
            for field in ("bearing", "defining_provision", "size_class"):
                if not isinstance(value.get(field), str) or not value[field].strip():
                    raise ClosureError(
                        f"{eli}: pending bearing supplement requires {field}"
                    )
            target_modules = value.get("target_module")
            if (
                not isinstance(target_modules, list)
                or target_modules != sorted(set(target_modules))
                or not target_modules
                or not set(target_modules).issubset(rulespec_paths)
            ):
                raise ClosureError(
                    f"{eli}: pending supplement has invalid target modules"
                )
            if value["size_class"] not in {"S", "M", "L"}:
                raise ClosureError(f"{eli}: invalid size_class")
        else:
            if value.get("bears_on_computed_surface") is not False:
                raise ClosureError(
                    f"{eli}: a bearing search supplement may not be excluded"
                )
            if set(value) & {
                "bearing",
                "defining_provision",
                "encoded_by",
                "size_class",
                "target_module",
            }:
                raise ClosureError(
                    f"{eli}: excluded supplement carries encoded/open-work fields"
                )
        rows.append(value)
        keys.append(eli)
    if keys != sorted(set(keys)):
        raise ClosureError("NZ supplemental instruments are not unique and sorted")

    receipts = decisions.get("discovery_receipts")
    if not isinstance(receipts, dict) or set(receipts) != {
        "subject_matter_search",
        "corpus_citation_scan",
    }:
        raise ClosureError("NZ discovery receipts have unexpected or missing channels")
    search = receipts.get("subject_matter_search")
    if not isinstance(search, dict) or set(search) != {
        "excluded_leads",
        "queries",
        "result_elis",
        "searched_at",
        "sources",
    }:
        raise ClosureError("NZ subject-matter search receipt has invalid shape")
    if not isinstance(search.get("searched_at"), str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", search["searched_at"]
    ):
        raise ClosureError("NZ subject-matter search date is malformed")
    for field in ("queries", "result_elis", "sources"):
        values = search.get(field)
        if (
            not isinstance(values, list)
            or values != sorted(set(values))
            or not values
            or not all(isinstance(value, str) and value for value in values)
        ):
            raise ClosureError(f"NZ subject-matter search {field} is malformed")
    excluded_leads = search.get("excluded_leads")
    if (
        not isinstance(excluded_leads, list)
        or not excluded_leads
        or not all(
            isinstance(row, dict)
            and set(row) == {"url", "reason"}
            and all(isinstance(row[field], str) and row[field] for field in row)
            for row in excluded_leads
        )
    ):
        raise ClosureError("NZ subject-matter excluded leads are malformed")
    discovered = set(search["result_elis"])
    subject_rows = {
        str(row["eli"])
        for row in rows
        if "subject_matter_search" in row["discovery_channels"]
    }
    if discovered != subject_rows:
        raise ClosureError("NZ subject-matter search result coverage drifted")
    citation_scan = receipts.get("corpus_citation_scan")
    if not isinstance(citation_scan, dict) or set(citation_scan) != {
        "approximation",
        "implementation_issue",
        "inspected_clone_commit",
        "pinned_release_commit",
        "reason",
        "scanned_at",
        "status",
    }:
        raise ClosureError("NZ corpus citation-scan receipt has invalid shape")
    if (
        citation_scan.get("inspected_clone_commit")
        != "2794b5448e81525f0ee351cdac2a49d32327aade"
        or citation_scan.get("pinned_release_commit") != CORPUS_RELEASE_SHA
        or citation_scan.get("implementation_issue") != "axiom-corpus#611"
        or citation_scan.get("status")
        != "official-scanner-not-runnable-no-nz-extractor"
        or not isinstance(citation_scan.get("reason"), str)
        or not citation_scan["reason"].strip()
        or not isinstance(citation_scan.get("scanned_at"), str)
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", citation_scan["scanned_at"])
    ):
        raise ClosureError("NZ corpus citation-scan receipt is malformed")
    approximation = citation_scan.get("approximation")
    expected_approximation = {
        "artifact": "conformance/closure/nz-citation-scan-approximation.tsv",
        "method": (
            "read-only exact-title inbound scan over every body in the pinned "
            "NZ statute and regulation JSONL files; excludes self-act hits; "
            "discovery leads only, not axiom-corpus#611 completeness"
        ),
        "provision_rows_scanned": 10171,
        "sha256": "7ffb680aa7962be6556e7b28291396a57bb04dc7004eb151eb26d3070c9dc988",
        "summary_artifact": (
            "conformance/closure/nz-citation-scan-approximation-summary.tsv"
        ),
        "summary_sha256": (
            "1d79f965037584a7c788b64f73db3f53869138b6238ab8d32f7474b27b46191f"
        ),
        "target_counts": {
            "Accident Compensation Act 2001": 70,
            "Income Tax Act 2007": 410,
            "Social Security Act 2018": 80,
        },
        "source_instrument_count": 20,
        "new_frontier_count": 13,
        "source_dispositions": _citation_scan_source_dispositions(),
        "source_target_match_rows": 560,
        "distinct_source_provision_paths": 535,
    }
    if not isinstance(approximation, dict) or approximation != expected_approximation:
        raise ClosureError("NZ citation-scan approximation receipt drifted")
    if (
        sum(
            int(row["source_target_match_rows"])
            for row in approximation["source_dispositions"]
        )
        != approximation["source_target_match_rows"]
    ):
        raise ClosureError("NZ citation-scan source hit coverage does not reconcile")
    if (
        sum(
            int(row["distinct_source_provision_paths"])
            for row in approximation["source_dispositions"]
        )
        != approximation["distinct_source_provision_paths"]
    ):
        raise ClosureError("NZ citation-scan distinct path coverage does not reconcile")
    supplemental_refs = {
        str(row["eli"])
        for row in rows
        if "corpus_citation_scan_approximation" in row["discovery_channels"]
    }
    expected_supplemental_refs = {
        str(row["frontier_ref"])
        for row in approximation["source_dispositions"]
        if row["resolution"] == "supplemental"
    }
    if supplemental_refs != expected_supplemental_refs:
        raise ClosureError("NZ citation-scan supplemental disposition coverage drifted")
    graph_refs = {
        str(row["frontier_ref"])
        for row in approximation["source_dispositions"]
        if row["resolution"] == "instrument_graph"
    }
    if not graph_refs.issubset(graph_elis):
        raise ClosureError("NZ citation-scan graph disposition coverage drifted")
    spine_refs = {
        str(row["frontier_ref"])
        for row in approximation["source_dispositions"]
        if row["resolution"] == "spine_root"
    }
    if spine_refs != set(INSTRUMENT_ACTS):
        raise ClosureError("NZ citation-scan spine-root coverage drifted")
    for path_key, sha_key in (
        ("artifact", "sha256"),
        ("summary_artifact", "summary_sha256"),
    ):
        artifact_path = REPO_ROOT / approximation[path_key]
        if (
            not artifact_path.is_file()
            or hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            != approximation[sha_key]
        ):
            raise ClosureError(
                f"NZ citation-scan approximation {path_key} is missing or drifted"
            )
    return rows


def _decision(
    status: str,
    *,
    classification: str | None = None,
    reason: str | None = None,
    encoded_by: str | None = None,
    bearing: str | None = None,
    bears_on_computed_surface: bool | None = None,
    defining_provision: str | None = None,
    size_class: str | None = None,
    target_module: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"status": status}
    for key, value in (
        ("classification", classification),
        ("reason", reason),
        ("encoded_by", encoded_by),
        ("bearing", bearing),
        ("bears_on_computed_surface", bears_on_computed_surface),
        ("defining_provision", defining_provision),
        ("size_class", size_class),
        ("target_module", target_module),
    ):
        if value is not None:
            row[key] = value
    return row


def _seed_instrument_decision(program: str, row: Mapping[str, Any]) -> dict[str, Any]:
    eli = str(row["eli"])
    title = str(row["title"])
    pair = (program, eli)
    encoded: dict[tuple[str, str], tuple[str, str]] = {
        (
            "nz/acc-earners-levy",
            "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2025/18/en/latest/",
        ): (
            "nz/regulations/acc/earners_levy.yaml",
            "Regulations 4 and 5 set the certified levy rates and maximum earnings caps.",
        ),
        (
            "nz/acc-earners-levy",
            "https://www.ird.govt.nz/en/income-tax/income-tax-for-individuals/acc-clients-and-carers/acc-earners-levy-rates",
        ): (
            "nz/regulations/acc/earners_levy.yaml",
            "Named parameter source for GST-inclusive levy rates, caps, and rounding.",
        ),
        (
            "nz/accommodation-supplement",
            "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2018/202/en/latest/",
        ): (
            "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "Regulations 15 and 18–19 supply encoded asset, abatement, and rounding rules.",
        ),
        (
            "nz/accommodation-supplement",
            "https://www.workandincome.govt.nz/products/benefit-rates/benefit-rates-april-2026.html",
        ): (
            "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "Named corroborating parameter source for the 1 April 2026 maximum rates.",
        ),
        (
            "nz/main-benefits",
            "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2026/36/en/latest/",
        ): (
            "nz/statutes/social_security/main_benefits/rates.yaml",
            "The 2026 order sets the encoded main-benefit rates from 1 April 2026.",
        ),
        (
            "nz/working-for-families",
            "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2025/260/en/latest/",
        ): (
            "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            "The order sets the encoded 2026–27 FTC, MFTC, and Best Start amounts.",
        ),
    }
    wff_guidance = {
        "https://www.ird.govt.nz/working-for-families/types/family-tax-credit",
        "https://www.ird.govt.nz/working-for-families/types/in-work-tax-credit",
        "https://www.ird.govt.nz/best-start",
        "https://www.ird.govt.nz/working-for-families/types/minimum-family-tax-credit",
        "https://www.ird.govt.nz/in-work-tax-credit-increase",
    }
    if program == "nz/working-for-families" and eli in wff_guidance:
        encoded[pair] = (
            "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            "Inland Revenue guidance is named by, and agrees with, the encoded WFF parameter surface.",
        )
    if pair in encoded:
        encoded_by, reason = encoded[pair]
        return _decision(
            "encoded",
            classification="parameter_or_rule_source",
            reason=reason,
            encoded_by=encoded_by,
            bears_on_computed_surface=True,
        )

    input_boundary: dict[tuple[str, str], tuple[str, str]] = {
        (
            "nz/acc-earners-levy",
            "https://www.ird.govt.nz/deductions-from-salary-and-wages",
        ): (
            "corroborating_levy_guidance",
            "The corpus inventory records that this PAYE guidance also covers ACC earners' levy deductions. It bears on the certified levy surface but supplies no separate parameter beyond the encoded Earners' Levy Regulations and the separately encoded IRD levy-rate page.",
        ),
        (
            "nz/main-benefits",
            "https://www.workandincome.govt.nz/products/benefit-rates/benefit-rates-april-2026.html",
        ): (
            "corroborating_rate_guidance",
            "The page independently corroborates the 1 April 2026 rates, but the pinned module names and proves the 2026 rates order rather than this guidance page.",
        ),
        (
            "nz/main-benefits",
            "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2018/202/en/latest/",
        ): (
            "input_derivation_rule",
            "The regulations govern assessable-income and administration inputs supplied to the claimed rate calculation; those upstream case determinations are not claimed.",
        ),
        (
            "nz/accommodation-supplement",
            "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2026/36/en/latest/",
        ): (
            "input_derivation_rule",
            "The order supplies the case-provided base-rate input used by the Accommodation Supplement entry-threshold formula.",
        ),
        (
            "nz/independent-earner-tax-credit",
            "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2025/260/en/latest/",
        ): (
            "input_derivation_rule",
            "The WFF order affects the case-supplied WFF-entitlement disqualifier consumed by the IETC rule, not the IETC formula itself.",
        ),
    }
    if program == "nz/independent-earner-tax-credit" and eli in wff_guidance:
        input_boundary[pair] = (
            "input_derivation_rule",
            "This WFF guidance governs the case-supplied WFF-entitlement disqualifier consumed by IETC; upstream entitlement classification is not claimed.",
        )
    is_statement = eli.endswith("/is-26-12")
    is_determination = "/determinations/emergency-events/2026/det-26-" in eli
    if program in {
        "nz/working-for-families",
        "nz/independent-earner-tax-credit",
    } and (is_statement or is_determination):
        input_boundary[pair] = (
            "interpretive_input_boundary" if is_statement else "input_derivation_rule",
            (
                "The instrument governs classification of amounts supplied through the explicit family_scheme_other_payments_not_excluded and related case-input boundary; the certificate does not claim event, payment, trust, or company adjudication upstream of those inputs."
            ),
        )
    inherited_encoded: dict[tuple[str, str], str] = {}
    if program == "nz/independent-earner-tax-credit" and eli in wff_guidance:
        inherited_encoded[pair] = (
            "nz/statutes/income_tax/family_scheme/tax_credits.yaml"
        )
    inherited_encoded.update(
        {
            (
                "nz/independent-earner-tax-credit",
                "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2025/260/en/latest/",
            ): "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            (
                "nz/accommodation-supplement",
                "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2026/36/en/latest/",
            ): "nz/statutes/social_security/main_benefits/rates.yaml",
            (
                "nz/main-benefits",
                "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2018/202/en/latest/",
            ): "nz/statutes/social_security/accommodation_supplement/core.yaml",
            (
                "nz/main-benefits",
                "https://www.workandincome.govt.nz/products/benefit-rates/benefit-rates-april-2026.html",
            ): "nz/statutes/social_security/main_benefits/rates.yaml",
        }
    )
    if pair in inherited_encoded:
        return _decision(
            "encoded",
            classification="encoded_in_shared_composition_module",
            reason=(
                "V3 re-disposition: the instrument is proof-bound by the named shared composition module. Any unencoded cross-module eligibility or input derivation remains separately open in the typed dependency ledger."
            ),
            encoded_by=inherited_encoded[pair],
            bears_on_computed_surface=True,
        )
    if pair in input_boundary:
        classification, reason = input_boundary[pair]
        bearing = "documented case-input or nonclaimed upstream surface"
        if classification == "corroborating_rate_guidance":
            bearing = "independent official rate corroboration; not an encoded source"
        elif classification == "corroborating_levy_guidance":
            bearing = "ACC levy deduction guidance; no separate encoded parameter"
        elif is_statement and program == "nz/working-for-families":
            reason = (
                "IS 26/12 interprets family-scheme-income categories. The certified "
                "subgraph encodes the statutory arithmetic in "
                "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml; "
                "taxpayer company, trust, control, payment, and event facts enter "
                "through explicit case inputs, and the statement sets no separate "
                "numeric parameter claimed by the certificate."
            )
            bearing = (
                "interpretive guidance over an encoded statutory module and its "
                "explicit taxpayer-fact inputs"
            )
        target_module = {
            "nz/acc-earners-levy": "nz/regulations/acc/earners_levy.yaml",
            "nz/accommodation-supplement": "nz/statutes/social_security/accommodation_supplement/core.yaml",
            "nz/independent-earner-tax-credit": "nz/statutes/income_tax/credits/individual_credits.yaml",
            "nz/main-benefits": "nz/statutes/social_security/main_benefits/rates.yaml",
            "nz/working-for-families": "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
        }[program]
        if eli.endswith("/2026/36/en/latest/"):
            defining_provision = "Social Security (Rates of Benefits and Allowances) Order 2026; Social Security Regulations 2018 reg 17"
            size_class = "M"
        elif eli.endswith("/2018/202/en/latest/"):
            defining_provision = "Social Security Regulations 2018 income and administration provisions bearing on the main-benefit rate surface"
            size_class = "L"
        elif eli.endswith("/2025/260/en/latest/"):
            defining_provision = "Income Tax (Tax Credit) Order 2025; Income Tax Act 2007 s LC 13 WFF disqualifier"
            size_class = "S"
        elif is_determination:
            defining_provision = "Income Tax Act 2007 s MB 13 emergency-event payment exclusion, as applied by the named determination"
            size_class = "S"
        elif is_statement:
            defining_provision = "IS 26/12 interpretation of Income Tax Act 2007 subpart MB family scheme income"
            size_class = "L"
        elif eli in wff_guidance:
            defining_provision = "Income Tax Act 2007 s LC 13 WFF-entitlement disqualifier and the guidance's named WFF credit provisions"
            size_class = "M"
        elif eli.endswith("deductions-from-salary-and-wages"):
            defining_provision = "ACC earners' levy deduction mechanics in Inland Revenue salary-and-wages guidance"
            size_class = "S"
        else:
            defining_provision = (
                "2026 main-benefit rate publication and its cited rate provisions"
            )
            size_class = "S"
        return _decision(
            "pending",
            reason=(
                f"V3 bearing rule: {reason} The instrument must be encoded; a documented input boundary cannot close it."
            ),
            bearing=bearing,
            bears_on_computed_surface=True,
            defining_provision=defining_provision,
            target_module=target_module,
            size_class=size_class,
        )

    weekly_compensation = row.get("corpus_citation_path", "").startswith(
        "nz/guidance/acc/"
    )
    duplicate_fact_sheet = eli.endswith("/is-26-12-fs-1")
    manifest_nonbearing = eli in {
        "https://www.ird.govt.nz/rwt-rate",
        "https://www.ird.govt.nz/deductions-from-salary-and-wages",
    }
    program_specific_nonbearing = (
        program == "nz/income-tax"
        and (
            eli in wff_guidance
            or is_statement
            or is_determination
            or eli.endswith("/2025/260/en/latest/")
        )
    ) or (
        program == "nz/winter-energy-payment"
        and eli
        in {
            "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2018/202/en/latest/",
            "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/2026/36/en/latest/",
            "https://www.workandincome.govt.nz/products/benefit-rates/benefit-rates-april-2026.html",
        }
    )
    if weekly_compensation:
        return _decision(
            "excluded-with-reason",
            classification="no_computational_bearing",
            reason=(
                "ACC weekly-compensation/client-payment guidance concerns entitlement payments, not the certified earners' levy calculation."
            ),
            bears_on_computed_surface=False,
        )
    if duplicate_fact_sheet:
        if program in {
            "nz/income-tax",
            "nz/independent-earner-tax-credit",
            "nz/working-for-families",
        }:
            return _decision(
                "pending",
                reason=(
                    "V3 bearing rule: the IS 26/12 fact sheet summarizes an interpretation that bears on family-scheme-income and the IETC WFF gate; duplication does not permit classification around it."
                ),
                bearing="summary guidance over family-scheme-income classifications and the IETC WFF gate",
                bears_on_computed_surface=True,
                defining_provision="IS 26/12 FS 1 summary of Income Tax Act 2007 subpart MB and s LC 13",
                target_module=(
                    "nz/statutes/income_tax/credits/individual_credits.yaml"
                    if program == "nz/independent-earner-tax-credit"
                    else "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml"
                ),
                size_class="S",
            )
        return _decision(
            "excluded-with-reason",
            classification="duplicative_summary",
            reason="Fact sheet adds no rule beyond IS 26/12, which is separately dispositioned.",
            bears_on_computed_surface=False,
        )
    if manifest_nonbearing or program_specific_nonbearing:
        return _decision(
            "excluded-with-reason",
            classification="no_computational_bearing",
            reason=f"{title} does not alter this certified program's claimed output surface.",
            bears_on_computed_surface=False,
        )
    if row.get("in_force") is False:
        application_end = row.get("application_end")
        if isinstance(application_end, str):
            reason = (
                f"{title}'s authoritative application period ended "
                f"{application_end}, before the certified 2026–27 period."
            )
        else:
            reason = (
                f"{title} is marked not in force in the authoritative PCO snapshot."
            )
        return _decision(
            "excluded-with-reason",
            classification="not_in_force",
            reason=reason,
            bears_on_computed_surface=False,
        )
    return _decision("pending")


def _subject_search_supplements() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "eli": "https://www.legislation.govt.nz/act/public/2024/19/en/latest/",
            "title_short": "Taxation (Budget Measures) Act 2024",
            "programs": [
                "nz/income-tax",
                "nz/independent-earner-tax-credit",
                "nz/working-for-families",
            ],
            "status": "encoded",
            "provenance": "Official legislation page and provisions read 2026-08-20.",
            "discovery_channels": ["subject_matter_search"],
            "bears_on_computed_surface": True,
            "reason": (
                "Sections 26–29 and 37 set the IETC ceiling, IWTC/MFTC amounts, "
                "and individual tax bands already proof-bound in the named modules."
            ),
            "encoded_by": [
                "nz/statutes/income_tax/credits/individual_credits.yaml",
                "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
                "nz/statutes/income_tax/schedule_1/individual_income_tax.yaml",
            ],
        },
        {
            "eli": "https://www.legislation.govt.nz/act/public/2026/8/en/latest/",
            "title_short": "Taxation (Annual Rates for 2025–26, Compliance Simplification, and Remedial Measures) Act 2026",
            "programs": ["nz/working-for-families"],
            "status": "encoded",
            "provenance": "Official legislation page and provisions read 2026-08-20.",
            "discovery_channels": ["subject_matter_search"],
            "bears_on_computed_surface": True,
            "reason": (
                "Sections 2 and 105 make the 2026–27 IWTC change from NZD 5,070 "
                "to NZD 7,670; the tax-credit module proof-binds both provisions."
            ),
            "encoded_by": ["nz/statutes/income_tax/family_scheme/tax_credits.yaml"],
        },
        {
            "eli": "https://www.legislation.govt.nz/act/public/2025/9/en/latest/",
            "title_short": "Taxation (Annual Rates for 2024–25, Emergency Response, and Remedial Measures) Act 2025",
            "programs": ["nz/independent-earner-tax-credit"],
            "status": "pending",
            "provenance": "Official legislation page and section 105 read 2026-08-20.",
            "discovery_channels": ["subject_matter_search"],
            "bears_on_computed_surface": True,
            "reason": (
                "Section 105 amended LC 13(1)(d)–(e) from 30 March 2025. The "
                "current module implements NOT(entitled OR receives), while the "
                "amended text requires NOT(entitled AND receives)."
            ),
            "bearing": "IETC WFF-entitlement status gate",
            "defining_provision": "Taxation (Annual Rates for 2024–25, Emergency Response, and Remedial Measures) Act 2025 s 105; Income Tax Act 2007 s LC 13(1)(d)–(e)",
            "target_module": ["nz/statutes/income_tax/credits/individual_credits.yaml"],
            "size_class": "S",
        },
        {
            "eli": "https://www.taxtechnical.ird.govt.nz/-/media/project/ir/tt/pdfs/tib/volume-37---2025/tib-vol37-no5.pdf",
            "title_short": "Tax Information Bulletin Vol 37 No 5 — Clarifying IETC eligibility",
            "programs": ["nz/independent-earner-tax-credit"],
            "status": "pending",
            "provenance": "Official Inland Revenue TIB PDF read 2026-08-20.",
            "discovery_channels": ["subject_matter_search"],
            "bears_on_computed_surface": True,
            "reason": "Official explanation of the amended LC 13 IETC eligibility test; not source-bound by the current module.",
            "bearing": "IETC WFF-entitlement status gate",
            "defining_provision": "TIB Vol 37 No 5, Clarifying IETC eligibility; Income Tax Act 2007 s LC 13",
            "target_module": ["nz/statutes/income_tax/credits/individual_credits.yaml"],
            "size_class": "S",
        },
        {
            "eli": "https://www.legislation.govt.nz/act/public/2025/26/en/latest/",
            "title_short": "Taxation (Budget Measures) Act 2025",
            "programs": ["nz/working-for-families"],
            "status": "pending",
            "provenance": "Official legislation page and provisions read 2026-08-20.",
            "discovery_channels": ["subject_matter_search"],
            "bears_on_computed_surface": True,
            "reason": (
                "Sections 2(5), 7, 8, and 16 amend MD 13, MG 3, and Schedule "
                "31. Numeric values are present, but the first-year Best Start "
                "gate and annualisation remain case-derived inputs."
            ),
            "bearing": "WFF abatement, Best Start first-year gate, and annualisation",
            "defining_provision": "Taxation (Budget Measures) Act 2025 ss 2(5), 7, 8, 16; Income Tax Act 2007 ss MD 13, MG 3 and Schedule 31",
            "target_module": [
                "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
                "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            ],
            "size_class": "M",
        },
        {
            "eli": "https://www.legislation.govt.nz/act/public/2025/27/en/latest/",
            "title_short": "Social Assistance Legislation (Accommodation Supplement and Income-related Rent) Amendment Act 2025",
            "programs": ["nz/accommodation-supplement"],
            "status": "pending",
            "provenance": "Official legislation page and provisions read 2026-08-20.",
            "discovery_channels": ["subject_matter_search"],
            "bears_on_computed_surface": True,
            "reason": (
                "Sections 2 and 4–15 change accommodation-cost definitions, "
                "entitlement/zero-rate rules, review mechanics, income exclusions, "
                "and weekly qualifying-cost/income terms."
            ),
            "bearing": "Accommodation Supplement eligibility, cost, income, and payment surface",
            "defining_provision": "Social Assistance Legislation (Accommodation Supplement and Income-related Rent) Amendment Act 2025 ss 2, 4–15",
            "target_module": [
                "nz/statutes/social_security/accommodation_supplement/core.yaml"
            ],
            "size_class": "L",
        },
        {
            "eli": "https://www.legislation.govt.nz/act/public/2026/27/en/latest/",
            "title_short": "Social Security (Modernisation) Amendment Act 2026",
            "programs": [
                "nz/accommodation-supplement",
                "nz/main-benefits",
                "nz/winter-energy-payment",
            ],
            "status": "pending",
            "provenance": "Official legislation page and in-period provisions read 2026-08-20.",
            "discovery_channels": ["subject_matter_search"],
            "bears_on_computed_surface": True,
            "reason": (
                "In-period sections 4–13, 19, 21, 33–34, 43–65 and schedules "
                "change main-benefit eligibility/review, work tests, WEP termination, "
                "ACC interaction, end/death rules, and regulation powers."
            ),
            "bearing": "Main-benefit, WEP, and Accommodation Supplement eligibility and continuation",
            "defining_provision": "Social Security (Modernisation) Amendment Act 2026 ss 4–13, 19, 21, 33–34, 43–65 and schedules",
            "target_module": [
                "nz/statutes/social_security/accommodation_supplement/core.yaml",
                "nz/statutes/social_security/main_benefits/entitlement.yaml",
                "nz/statutes/social_security/winter_energy_payment/core.yaml",
            ],
            "size_class": "L",
        },
        {
            "eli": "https://www.taxtechnical.ird.govt.nz/case-summaries/2023/csum-23-04",
            "title_short": "TRA 005/21 [2023] NZTRA 1 (CSUM 23/04)",
            "programs": [
                "nz/independent-earner-tax-credit",
                "nz/working-for-families",
            ],
            "status": "pending",
            "provenance": "Official Inland Revenue case summary read 2026-08-20.",
            "discovery_channels": ["subject_matter_search"],
            "bears_on_computed_surface": True,
            "reason": "Current de-facto-relationship precedent bears on WFF caregiver/partner gates and therefore the IETC WFF disqualifier.",
            "bearing": "WFF relationship, principal-caregiver, and partner allocation gates",
            "defining_provision": "TRA 005/21 [2023] NZTRA 1; Income Tax Act 2007 ss CB 32, MC 4, MC 7, MC 8, MC 11, YA 1; Legislation Act 2019 ss 13–14",
            "target_module": ["nz/statutes/income_tax/family_scheme/eligibility.yaml"],
            "size_class": "M",
        },
        {
            "eli": "https://www.taxtechnical.ird.govt.nz/-/media/project/ir/tt/pdfs/tib/volume-37---2025/tib-vol37-no7.pdf",
            "title_short": "Tax Information Bulletin Vol 37 No 7 — Budget 2025 WFF commentary",
            "programs": ["nz/working-for-families"],
            "status": "pending",
            "provenance": "Official Inland Revenue TIB PDF read 2026-08-20.",
            "discovery_channels": ["subject_matter_search"],
            "bears_on_computed_surface": True,
            "reason": "Official Budget 2025 commentary bears on MD 13, MG 3, and Schedule 31 but is not source-bound by the current modules.",
            "bearing": "WFF abatement, Best Start first-year gate, and annualisation",
            "defining_provision": "TIB Vol 37 No 7 Budget 2025 WFF commentary; Income Tax Act 2007 ss MD 13, MG 3 and Schedule 31",
            "target_module": [
                "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
                "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
            ],
            "size_class": "M",
        },
        {
            "eli": "https://www.taxtechnical.ird.govt.nz/-/media/project/ir/tp/publications/2026/compliance-simplification-bill-act-commentary.pdf",
            "title_short": "Taxation (Annual Rates 2025–26, Compliance Simplification, and Remedial Measures) Act 2026 commentary",
            "programs": ["nz/working-for-families"],
            "status": "pending",
            "provenance": "Official Inland Revenue Act commentary PDF read 2026-08-20.",
            "discovery_channels": ["subject_matter_search"],
            "bears_on_computed_surface": True,
            "reason": "Official commentary on the 2026 Act's section 105 IWTC change is not source-bound by the current tax-credit module.",
            "bearing": "2026–27 IWTC amount change",
            "defining_provision": "Official 2026 Act commentary, section 105 IWTC article",
            "target_module": ["nz/statutes/income_tax/family_scheme/tax_credits.yaml"],
            "size_class": "S",
        },
        {
            "eli": "https://www.legislation.govt.nz/act/public/2026/25/en/latest/",
            "title_short": "Taxation (Budget Measures) Act 2026",
            "programs": ["nz/working-for-families"],
            "status": "excluded-with-reason",
            "provenance": "Official legislation page and commencement provisions read 2026-08-20.",
            "discovery_channels": ["subject_matter_search"],
            "bears_on_computed_surface": False,
            "reason": (
                "The WFF/family-scheme provisions commence 1 April 2027, after "
                "the certified period ending 31 March 2027; earlier portions bear "
                "only on spine-excluded surfaces."
            ),
        },
    ]
    rows.extend(
        [
            {
                "eli": "https://www.legislation.govt.nz/act/public/1973/5/en/latest/",
                "title_short": "Rates Rebate Act 1973",
                "programs": ["nz/accommodation-supplement"],
                "status": "excluded-with-reason",
                "provenance": "Pinned-corpus exact-title citation scan and provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": False,
                "reason": "The Act consumes rates, income, and benefit facts to compute a separate rates rebate; it is downstream of, not upstream of, the certified outputs.",
            },
            {
                "eli": "https://www.legislation.govt.nz/act/public/1985/141/en/latest/",
                "title_short": "Goods and Services Tax Act 1985",
                "programs": ["nz/acc-earners-levy"],
                "status": "pending",
                "provenance": "Pinned-corpus exact-title citation scan and official provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": True,
                "reason": "Sections 5(6EC)–(6EE), 8(1), and 10 make the earners' levy a GST-bearing deemed supply and supply the 15 percent tax factor used by the levy surface.",
                "bearing": "GST treatment and factor in the earners' levy calculation",
                "defining_provision": "Goods and Services Tax Act 1985 ss 5(6EC)–(6EE), 8(1), 10",
                "target_module": ["nz/regulations/acc/earners_levy.yaml"],
                "size_class": "S",
            },
            {
                "eli": "https://www.legislation.govt.nz/act/public/1987/129/en/latest/",
                "title_short": "Parental Leave and Employment Protection Act 1987",
                "programs": ["nz/working-for-families"],
                "status": "excluded-with-reason",
                "provenance": "Pinned-corpus exact-title citation scan and provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": False,
                "reason": "The composition consumes an actual parental-leave/preterm-payment register entry as an observable act; it does not compute entitlement or payment under this Act.",
            },
            {
                "eli": "https://www.legislation.govt.nz/act/public/1991/142/en/latest/",
                "title_short": "Child Support Act 1991",
                "programs": ["nz/working-for-families"],
                "status": "excluded-with-reason",
                "provenance": "Pinned-corpus exact-title citation scan and provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": False,
                "reason": "Child-support liability and payment are downstream interactions outside the certified tax, credit, levy, and benefit output surface.",
            },
            {
                "eli": "https://www.legislation.govt.nz/act/public/1992/76/en/latest/",
                "title_short": "Public and Community Housing Management Act 1992",
                "programs": ["nz/accommodation-supplement"],
                "status": "pending",
                "provenance": "Pinned-corpus exact-title citation scan and official provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": True,
                "reason": "Section 2 defines additional resident, applicable person, contributions, and social housing, which the Social Security Act imports into Accommodation Supplement cost and exclusion mechanics.",
                "bearing": "Social-housing additional-resident and contribution inputs",
                "defining_provision": "Public and Community Housing Management Act 1992 s 2; Social Security Act 2018 ss 65AAA–66",
                "target_module": [
                    "nz/statutes/social_security/accommodation_supplement/core.yaml"
                ],
                "size_class": "M",
            },
            {
                "eli": "https://www.legislation.govt.nz/act/public/1994/166/en/latest/",
                "title_short": "Tax Administration Act 1994",
                "programs": [
                    "nz/independent-earner-tax-credit",
                    "nz/working-for-families",
                ],
                "status": "pending",
                "provenance": "Pinned-corpus exact-title citation scan and official provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": True,
                "reason": "Sections 80KA–80KW govern WFF entitlement, payment, and cadence, while s 91AAS decisions feed the ITA s MB 13 emergency-event exclusion; the IETC gate depends on WFF entitlement and receipt.",
                "bearing": "WFF entitlement/payment administration and MB 13 emergency-event decisions",
                "defining_provision": "Tax Administration Act 1994 ss 80KA–80KW (especially ss 80KF, 80KO, 80KW) and 91AAS; Income Tax Act 2007 ss LC 13, MB 13",
                "target_module": [
                    "nz/statutes/income_tax/credits/individual_credits.yaml",
                    "nz/statutes/income_tax/family_scheme/family_scheme_income.yaml",
                    "nz/statutes/income_tax/family_scheme/tax_credits.yaml",
                ],
                "size_class": "L",
            },
            {
                "eli": "https://www.legislation.govt.nz/act/public/2001/84/en/latest/",
                "title_short": "New Zealand Superannuation and Retirement Income Act 2001",
                "programs": [
                    "nz/independent-earner-tax-credit",
                    "nz/winter-energy-payment",
                ],
                "status": "excluded-with-reason",
                "provenance": "Pinned-corpus exact-title citation scan and provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": False,
                "reason": "The composition consumes actual New Zealand Superannuation receipt as an MSD register fact; it does not compute Superannuation entitlement or amount.",
            },
            {
                "eli": "https://www.legislation.govt.nz/act/public/2006/40/en/latest/",
                "title_short": "KiwiSaver Act 2006",
                "programs": ["nz/income-tax"],
                "status": "excluded-with-reason",
                "provenance": "Pinned-corpus exact-title citation scan and provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": False,
                "reason": "KiwiSaver contribution, withdrawal, and scheme administration are outside the certified gross-income tax and transfer composition outputs.",
            },
            {
                "eli": "https://www.legislation.govt.nz/act/public/2009/51/en/latest/",
                "title_short": "Immigration Act 2009",
                "programs": [
                    "nz/accommodation-supplement",
                    "nz/independent-earner-tax-credit",
                    "nz/main-benefits",
                    "nz/working-for-families",
                ],
                "status": "excluded-with-reason",
                "provenance": "Pinned-corpus exact-title citation scan and provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": False,
                "reason": "The discovered ss 298–299 references concern information matching and recovery. Issued visa, refugee, and protected-person statuses enter only as immigration-register facts.",
            },
            {
                "eli": "https://www.legislation.govt.nz/act/public/2011/62/en/latest/",
                "title_short": "Student Loan Scheme Act 2011",
                "programs": ["nz/income-tax"],
                "status": "excluded-with-reason",
                "provenance": "Pinned-corpus exact-title citation scan and provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": False,
                "reason": "Student-loan repayment obligations are a downstream use of income-tax facts and are outside every certified output surface.",
            },
            {
                "eli": "https://www.legislation.govt.nz/act/public/2018/4/en/latest/",
                "title_short": "Customs and Excise Act 2018",
                "programs": ["nz/income-tax"],
                "status": "excluded-with-reason",
                "provenance": "Pinned-corpus exact-title citation scan and provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": False,
                "reason": "Customs duties and information-matching provisions do not alter the certified individual income-tax or transfer computations.",
            },
            {
                "eli": "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/1993/169/en/latest/",
                "title_short": "Health Entitlement Cards Regulations 1993",
                "programs": ["nz/main-benefits"],
                "status": "excluded-with-reason",
                "provenance": "Pinned-corpus exact-title citation scan and provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": False,
                "reason": "Community-services and health-card eligibility is downstream of income and benefit status and is outside the certified outputs.",
            },
            {
                "eli": "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/1998/277/en/latest/",
                "title_short": "Student Allowances Regulations 1998",
                "programs": ["nz/accommodation-supplement"],
                "status": "pending",
                "provenance": "Pinned-corpus exact-title citation scan and official provision review, 2026-08-20.",
                "discovery_channels": ["corpus_citation_scan_approximation"],
                "bears_on_computed_surface": True,
                "reason": "Regulations 2–8 and 12 define interpretation, continued allowances, basic and independent-circumstances grants, and general eligibility; the operative gate is expressly subject to regs 4–6, 12, 12A–16, 20, 26, 28–31, 34–35, 40, 44–46, 47B–47E, and 48 and is consumed by the Accommodation Supplement exclusion.",
                "bearing": "Student-allowance/grant eligibility gate for Accommodation Supplement",
                "defining_provision": "Student Allowances Regulations 1998 regs 2–8, 12, 12A–16, 20, 26, 28–31, 34–35, 40, 44–46, 47B–47E, 48; Social Security Act 2018 s 67",
                "target_module": [
                    "nz/statutes/social_security/accommodation_supplement/core.yaml"
                ],
                "size_class": "L",
            },
        ]
    )
    for row in rows:
        if row["eli"] == (
            "https://www.legislation.govt.nz/act/public/2026/8/en/latest/"
        ):
            row["discovery_channels"] = [
                "corpus_citation_scan_approximation",
                "subject_matter_search",
            ]
    rows.sort(key=lambda row: str(row["eli"]))
    return rows


def _instrument_discovery_receipts(
    supplements: list[dict[str, Any]],
) -> dict[str, Any]:
    queries = [
        'site:legislation.govt.nz "ACC earners\' levy" "2026"',
        'site:legislation.govt.nz "Clarifying IETC eligibility" "LC 13"',
        'site:legislation.govt.nz "Jobseeker Support" "1 April 2026" "Social Security"',
        'site:legislation.govt.nz "Sole Parent Support" "1 April 2026" "Social Security"',
        'site:legislation.govt.nz "Working for Families" "2026"',
        'site:legislation.govt.nz "accommodation supplement" "2026" "Social Security Act 2018"',
        'site:legislation.govt.nz "family scheme income" "2026"',
        'site:legislation.govt.nz "independent earner tax credit" "2026"',
        'site:legislation.govt.nz "independent earner tax credit" "30 March 2025"',
        'site:legislation.govt.nz "winter energy payment" "2026" "Social Security Act 2018"',
        'site:legislation.govt.nz/act/public "Accident Compensation Act 2001" "earners\' levy" 2026',
        'site:legislation.govt.nz/act/public/2025 "Section LC 13 amended"',
        'site:legislation.govt.nz/act/public/2025/26 "1 April 2026"',
        'site:legislation.govt.nz/act/public/2025/26 "Working for Families"',
        'site:legislation.govt.nz/act/public/2025/26 "family scheme"',
        'site:legislation.govt.nz/act/public/2025/26 "independent earner tax credit"',
        'site:taxtechnical.ird.govt.nz "ACC earners\' levy" 2026',
        'site:taxtechnical.ird.govt.nz "Clarifying IETC eligibility"',
        'site:taxtechnical.ird.govt.nz "family scheme income" 2026',
        'site:taxtechnical.ird.govt.nz "independent earner tax credit" 2026',
        'site:taxtechnical.ird.govt.nz "working for families" 2026 determination',
        'site:taxtechnical.ird.govt.nz/case-summaries "WFF tax credit" entitlement',
        'site:taxtechnical.ird.govt.nz/case-summaries "Working for Families" entitlement',
        'site:taxtechnical.ird.govt.nz/case-summaries "family scheme income"',
        'site:taxtechnical.ird.govt.nz/case-summaries "in-work tax credit"',
        'site:taxtechnical.ird.govt.nz/case-summaries "independent earner tax credit"',
        'site:taxtechnical.ird.govt.nz/case-summaries WfFTC "Income Tax Act 2007"',
        'site:taxtechnical.ird.govt.nz/new-legislation/act-articles "Working for Families" "$44,900"',
        'site:taxtechnical.ird.govt.nz/new-legislation/act-articles "in-work tax credit" "$7,670"',
        'site:taxtechnical.ird.govt.nz/new-legislation/act-articles "Taxation (Annual Rates for 2025–26, Compliance Simplification, and Remedial Measures) Act 2026"',
        'site:taxtechnical.ird.govt.nz/new-legislation/act-articles "Taxation (Budget Measures) Act 2025"',
    ]
    return {
        "subject_matter_search": {
            "searched_at": "2026-08-20",
            "sources": [
                "https://www.legislation.govt.nz",
                "https://www.taxtechnical.ird.govt.nz",
            ],
            "queries": sorted(queries),
            "result_elis": sorted(
                str(row["eli"])
                for row in supplements
                if "subject_matter_search" in row["discovery_channels"]
            ),
            "excluded_leads": [
                {
                    "url": "https://www.taxtechnical.ird.govt.nz/case-summaries/2026/csum-26-03",
                    "reason": (
                        "Abdullah Safi concerns TAA ss 141E/149A evasion-penalty "
                        "procedure after WFF reassessments were abandoned, not a "
                        "computed WFF rule."
                    ),
                }
            ],
        },
        "corpus_citation_scan": {
            "status": "official-scanner-not-runnable-no-nz-extractor",
            "implementation_issue": "axiom-corpus#611",
            "inspected_clone_commit": "2794b5448e81525f0ee351cdac2a49d32327aade",
            "pinned_release_commit": CORPUS_RELEASE_SHA,
            "scanned_at": "2026-08-20",
            "reason": (
                "The local corpus clone has only a US citation extractor; no NZ "
                "#611 implementation is present. A separately bound exact-title "
                "approximation was run read-only and is not represented as #611."
            ),
            "approximation": {
                "artifact": "conformance/closure/nz-citation-scan-approximation.tsv",
                "method": (
                    "read-only exact-title inbound scan over every body in the pinned "
                    "NZ statute and regulation JSONL files; excludes self-act hits; "
                    "discovery leads only, not axiom-corpus#611 completeness"
                ),
                "provision_rows_scanned": 10171,
                "sha256": "7ffb680aa7962be6556e7b28291396a57bb04dc7004eb151eb26d3070c9dc988",
                "summary_artifact": "conformance/closure/nz-citation-scan-approximation-summary.tsv",
                "summary_sha256": "1d79f965037584a7c788b64f73db3f53869138b6238ab8d32f7474b27b46191f",
                "target_counts": {
                    "Accident Compensation Act 2001": 70,
                    "Income Tax Act 2007": 410,
                    "Social Security Act 2018": 80,
                },
                "source_instrument_count": 20,
                "new_frontier_count": 13,
                "source_dispositions": _citation_scan_source_dispositions(),
                "source_target_match_rows": 560,
                "distinct_source_provision_paths": 535,
            },
        },
    }


def bootstrap_instrument_dispositions(graph: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for instrument in graph.get("instruments") or []:
        act = INSTRUMENT_ACTS[str(instrument["act_citation_path"])]
        for program in act["programs"]:
            rows.append(
                {
                    "program": program,
                    "eli": instrument["eli"],
                    **_seed_instrument_decision(str(program), instrument),
                }
            )
    rows.sort(key=lambda row: (row["program"], row["eli"]))
    supplements = _subject_search_supplements()
    return {
        "schema": "axiom_oracles.nz_instrument_dispositions.v3",
        "schema_compatibility_note": (
            "DK ledger-v2 committed_decisions.instrument_dispositions status and "
            "reason fields, repeated per program because instrument_graph.v1 has "
            "no multi-program disposition dimension; v3 additionally types bearing "
            "and binds mandatory discovery-channel supplements"
        ),
        "instrument_dispositions": rows,
        "supplemental_instruments": supplements,
        "discovery_receipts": _instrument_discovery_receipts(supplements),
    }


def _instrument_ledger_row(
    graph_row: Mapping[str, Any], decision: Mapping[str, Any]
) -> dict[str, Any]:
    row = {
        "eli": graph_row.get("eli"),
        "relation": graph_row.get("relation"),
        "title_short": graph_row.get("title_short"),
        "type_document": graph_row.get("type_document"),
        "in_force": graph_row.get("in_force"),
        "status": decision.get("status"),
    }
    for key in (
        "classification",
        "reason",
        "bearing",
        "encoded_by",
        "bears_on_computed_surface",
        "defining_provision",
        "size_class",
        "target_module",
    ):
        if decision.get(key) is not None:
            row[key] = decision[key]
    return row


def _supplemental_ledger_row(decision: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "eli": decision.get("eli"),
        "relation": "search_discovered",
        "title_short": decision.get("title_short"),
        "type_document": "search-discovered supplement",
        "in_force": True,
        "status": decision.get("status"),
        "provenance": decision.get("provenance"),
        "discovery_channels": decision.get("discovery_channels"),
        "programs": decision.get("programs"),
    }
    for key in (
        "reason",
        "bearing",
        "encoded_by",
        "bears_on_computed_surface",
        "defining_provision",
        "size_class",
        "target_module",
    ):
        if decision.get(key) is not None:
            row[key] = decision[key]
    return row


def _frontier_counts(ledger: list[dict[str, Any]]) -> dict[str, int]:
    """Count only disposition rows that actually exist in the ledger.

    An authoritative listing gap is a capture-completeness defect, not an
    invented instrument row.  Keep those unknown candidates in ``capture`` /
    ``capture_gaps`` and force ``complete=false`` without laundering them into
    the DK status counts or the pending-ELI list.
    """

    counts = {
        status: sum(row.get("status") == status for row in ledger)
        for status in INSTRUMENT_STATUSES
    }
    return {"total": len(ledger), **counts}


def _build_instrument_frontiers(
    graph: Mapping[str, Any],
    decisions: Mapping[str, Any],
    *,
    rulespec_paths: set[str],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    decision_by_pair = _canonical_instrument_decisions(
        graph, decisions, rulespec_paths=rulespec_paths
    )
    supplemental = _canonical_supplemental_instruments(
        graph, decisions, rulespec_paths=rulespec_paths
    )
    if decisions != bootstrap_instrument_dispositions(graph):
        raise ClosureError(
            "NZ instrument dispositions drifted from the audited bearing-rule producer"
        )
    graph_rows = list(graph["instruments"])
    receipt_by_act = {
        row["act_citation_path"]: row for row in graph["retrieval_receipts"]
    }
    program_frontiers: dict[str, dict[str, Any]] = {}
    for program, act_path in sorted(PROGRAM_INSTRUMENT_ACT.items()):
        selected = [row for row in graph_rows if row["act_citation_path"] == act_path]
        ledger = [
            _instrument_ledger_row(row, decision_by_pair[(program, str(row["eli"]))])
            for row in selected
        ]
        selected_supplements = [
            row for row in supplemental if program in row["programs"]
        ]
        ledger.extend(_supplemental_ledger_row(row) for row in selected_supplements)
        ledger.sort(key=lambda row: str(row["eli"]))
        receipt = receipt_by_act[act_path]
        unresolved = receipt["unresolved_count"]
        pending = [row["eli"] for row in ledger if row.get("status") == "pending"]
        reasons_complete = all(
            row.get("status") == "pending"
            or (isinstance(row.get("reason"), str) and bool(row["reason"].strip()))
            for row in ledger
        )
        program_frontiers[program] = {
            "instrument_count": receipt["captured_count"],
            "reported_instrument_count": receipt["reported_count"],
            "supplemental_count": (
                sum(row["relation"] == "bears_on" for row in selected)
                + len(selected_supplements)
            ),
            "counts": _frontier_counts(ledger),
            "pending": pending,
            "complete": (
                bool(selected)
                and receipt["complete"] is True
                and not pending
                and reasons_complete
            ),
            "capture": {
                "act_citation_path": act_path,
                "reported_count": receipt["reported_count"],
                "captured_count": receipt["captured_count"],
                "unresolved_count": unresolved,
                "complete": receipt["complete"],
            },
            "ledger": ledger,
        }

    global_ledger = []
    precedence = {
        "excluded-with-reason": 0,
        "classified-with-reason": 1,
        "encoded": 2,
        "pending": 3,
    }
    for graph_row in graph_rows:
        programs = INSTRUMENT_ACTS[str(graph_row["act_citation_path"])]["programs"]
        program_rows = [
            decision_by_pair[(str(program), str(graph_row["eli"]))]
            for program in programs
        ]
        status = max(
            (str(row["status"]) for row in program_rows), key=precedence.__getitem__
        )
        aggregate: dict[str, Any] = {"status": status}
        if status == "encoded":
            encoded_by = sorted(
                {
                    str(row["encoded_by"])
                    for row in program_rows
                    if row.get("status") == "encoded"
                }
            )
            aggregate.update(
                {
                    "classification": "encoded_in_at_least_one_program",
                    "reason": "At least one certified program encodes this instrument; see program_dispositions.",
                    "encoded_by": encoded_by[0],
                }
            )
        elif status == "classified-with-reason":
            aggregate.update(
                {
                    "classification": "classified_in_at_least_one_program",
                    "reason": "At least one certified program classifies this instrument at a documented boundary; see program_dispositions.",
                }
            )
        elif status == "excluded-with-reason":
            aggregate.update(
                {
                    "classification": "excluded_for_all_certified_programs",
                    "reason": "Every certified program empowered by this Act excludes this instrument with a reason; see program_dispositions.",
                }
            )
        row = _instrument_ledger_row(graph_row, aggregate)
        row["program_dispositions"] = [
            {
                "program": program,
                **decision_by_pair[(str(program), str(graph_row["eli"]))],
            }
            for program in programs
        ]
        global_ledger.append(row)

    global_ledger.extend(_supplemental_ledger_row(row) for row in supplemental)
    global_ledger.sort(key=lambda row: str(row["eli"]))

    capture_gaps = [
        {
            "act_citation_path": act_path,
            "unresolved_listing_rows": receipt["unresolved_count"],
        }
        for act_path, receipt in sorted(receipt_by_act.items())
        if receipt["unresolved_count"]
    ]
    global_pending = [
        row["eli"] for row in global_ledger if row.get("status") == "pending"
    ]
    global_frontier = {
        "instrument_count": sum(
            receipt["captured_count"] for receipt in receipt_by_act.values()
        ),
        "reported_instrument_count": sum(
            receipt["reported_count"] for receipt in receipt_by_act.values()
        ),
        "supplemental_count": (
            sum(row["relation"] == "bears_on" for row in graph_rows) + len(supplemental)
        ),
        "counts": _frontier_counts(global_ledger),
        "pending": global_pending,
        "complete": all(
            frontier["complete"] for frontier in program_frontiers.values()
        ),
        "capture_gaps": capture_gaps,
        "programs": {
            program: {
                "counts": frontier["counts"],
                "pending": len(frontier["pending"]),
                "complete": frontier["complete"],
            }
            for program, frontier in program_frontiers.items()
        },
        "ledger": global_ledger,
    }
    return global_frontier, program_frontiers


def _derive_requested_output_roots(
    trace: dict,
) -> tuple[dict[str, list[str]], dict[str, set[tuple[str, tuple[str, ...]]]]]:
    """Derive ownership exclusively from each execution-emitted trace row.

    ``PROGRAM_VIEWS`` deliberately does not participate here. It is the
    declaration side of the later bijection, not an ownership oracle for the
    execution evidence.
    """

    expected_keys = {
        "_comment",
        "capture",
        "compiled_program",
        "engine",
        "evaluation_count",
        "evaluations",
        "period",
        "rulespec_commit",
        "schema",
        "suite",
    }
    if set(trace) != expected_keys:
        raise ClosureError("NZ evaluation trace top-level shape drifted")
    if trace.get("schema") != TRACE_SCHEMA or trace.get("suite") != TRACE_SUITE:
        raise ClosureError("unexpected NZ evaluation trace schema or suite")
    if (
        trace.get("capture") != TRACE_CAPTURE
        or trace.get("compiled_program") != TRACE_COMPILED_PROGRAM
        or trace.get("engine") != TRACE_ENGINE
        or trace.get("rulespec_commit") != RULESPEC_SHA
        or trace.get("period") != {"start": "2026-04-01", "end": "2027-03-31"}
    ):
        raise ClosureError("NZ evaluation trace provenance drifted")
    evaluations = trace.get("evaluations")
    if (
        not isinstance(evaluations, list)
        or isinstance(trace.get("evaluation_count"), bool)
        or trace.get("evaluation_count") != len(evaluations)
        or len(evaluations) != TRACE_EVALUATION_COUNT
    ):
        raise ClosureError("NZ evaluation trace must contain 883 evaluations")

    derived: dict[str, set[str]] = {}
    canonical_requests: dict[str, set[tuple[str, tuple[str, ...]]]] = {}
    for index, evaluation in enumerate(evaluations, start=1):
        location = f"NZ evaluation trace row {index - 1}"
        if not isinstance(evaluation, dict) or set(evaluation) != {
            "evaluation_id",
            "request",
            "requested_output_roots",
            "response",
            "view",
        }:
            raise ClosureError(f"{location} has invalid canonical shape")
        if evaluation.get("evaluation_id") != f"nz-ie-eval-{index:04d}":
            raise ClosureError(f"{location} has a missing, duplicate, or reordered id")
        view = evaluation.get("view")
        if not isinstance(view, str) or not view:
            raise ClosureError(f"{location} has an invalid emitted view")
        request = evaluation.get("request")
        if (
            not isinstance(request, dict)
            or set(request) != {"dataset", "mode", "queries"}
            or request.get("mode") != "explain"
        ):
            raise ClosureError(f"{location} has an invalid explain request")
        dataset = request.get("dataset")
        if (
            not isinstance(dataset, dict)
            or set(dataset) != {"inputs", "relations"}
            or not isinstance(dataset.get("inputs"), list)
            or not dataset["inputs"]
            or dataset.get("relations") != []
        ):
            raise ClosureError(f"{location} has an invalid request dataset")
        queries = request.get("queries")
        if not isinstance(queries, list) or len(queries) != 1:
            raise ClosureError(f"{location} must contain exactly one query")
        query = queries[0]
        if not isinstance(query, dict) or set(query) != {
            "entity_id",
            "outputs",
            "period",
        }:
            raise ClosureError(f"{location} query has invalid canonical shape")
        outputs = query.get("outputs")
        if (
            not isinstance(outputs, list)
            or not outputs
            or outputs != list(dict.fromkeys(outputs))
            or not all(isinstance(output, str) and output for output in outputs)
        ):
            raise ClosureError(f"{location} has invalid requested outputs")
        if evaluation.get("requested_output_roots") != outputs:
            raise ClosureError(
                f"{location} requested_output_roots differ from request outputs"
            )
        expected_period = {
            "period_kind": "tax_year",
            "start": trace["period"]["start"],
            "end": trace["period"]["end"],
        }
        entity_id = query.get("entity_id")
        if (
            not isinstance(entity_id, str)
            or not entity_id
            or query.get("period") != expected_period
        ):
            raise ClosureError(f"{location} query entity or period drifted")
        response = evaluation.get("response")
        if (
            not isinstance(response, dict)
            or set(response) != {"entity_id", "metadata", "outputs", "period"}
            or response.get("entity_id") != entity_id
            or response.get("period") != expected_period
            or response.get("metadata")
            != {"actual_mode": "explain", "requested_mode": "explain"}
        ):
            raise ClosureError(f"{location} response envelope drifted")
        returned = response.get("outputs")
        if not isinstance(returned, dict) or set(returned) != set(outputs):
            raise ClosureError(
                f"{location} response outputs do not biject request outputs"
            )
        if any(
            not isinstance(returned[root], dict) or returned[root].get("id") != root
            for root in outputs
        ):
            raise ClosureError(f"{location} response output identity drifted")

        roots = tuple(outputs)
        derived.setdefault(view, set()).update(roots)
        canonical_requests.setdefault(_canonical_json(request), set()).add(
            (view, roots)
        )

    return (
        {view: sorted(roots) for view, roots in sorted(derived.items())},
        canonical_requests,
    )


def _validate_request_evidence_binding(
    evidence: dict,
    *,
    trace_roots: dict[str, list[str]],
    canonical_trace_requests: dict[str, set[tuple[str, tuple[str, ...]]]],
) -> None:
    """Bind the committed executable request subset to actual trace calls."""

    if evidence.get("schema") != "axiom_oracles.nz_executable_requests.v1":
        raise ClosureError("unexpected NZ executable request evidence schema")
    if evidence.get("provenance") != REQUEST_EVIDENCE_PROVENANCE:
        raise ClosureError("NZ executable request evidence provenance drifted")
    rows = evidence.get("requests")
    if not isinstance(rows, list) or not rows:
        raise ClosureError("NZ executable request evidence has no requests")
    seen_ids: set[str] = set()
    roots_from_matched_trace: dict[str, set[str]] = {}
    for index, row in enumerate(rows):
        location = f"NZ executable request evidence row {index}"
        if not isinstance(row, dict):
            raise ClosureError(f"{location} is invalid")
        request_id = row.get("id")
        if not isinstance(request_id, str) or not request_id or request_id in seen_ids:
            raise ClosureError(f"{location} has a missing or duplicate id")
        seen_ids.add(request_id)
        declared_program = row.get("program")
        if not isinstance(declared_program, str) or not declared_program:
            raise ClosureError(f"{location} has an invalid declared program")
        request = row.get("request")
        if not isinstance(request, dict):
            raise ClosureError(f"{location} has no canonical request")
        matches = canonical_trace_requests.get(_canonical_json(request))
        if not matches:
            raise ClosureError(
                f"{location} request/root is absent from the committed evaluation trace"
            )
        if len(matches) != 1:
            raise ClosureError(
                f"{location} has ambiguous ownership in the evaluation trace"
            )
        # Ownership comes from the matched trace evaluation. The evidence row's
        # program label is intentionally not used to normalize this side.
        view, requested_roots = next(iter(matches))
        if declared_program != view:
            raise ClosureError(
                f"{location} declared program differs from trace-emitted ownership"
            )
        roots_from_matched_trace.setdefault(view, set()).update(requested_roots)
    matched = {
        view: sorted(roots) for view, roots in sorted(roots_from_matched_trace.items())
    }
    if matched != trace_roots:
        raise ClosureError(
            "NZ executable request evidence does not cover the trace-derived root set"
        )
    if evidence.get("requested_outputs_by_program") != trace_roots:
        raise ClosureError(
            "NZ executable request evidence summary differs from trace-derived roots"
        )


def load_requested_output_roots(
    *,
    trace: dict | None = None,
    request_evidence: dict | None = None,
) -> dict[str, list[str]]:
    """Derive per-program roots from #476's committed execution trace."""

    if trace is None:
        if hashlib.sha256(EVALUATION_TRACE_PATH.read_bytes()).hexdigest() != (
            EVALUATION_TRACE_SHA256
        ):
            raise ClosureError(
                "NZ evaluation trace bytes changed; review and re-pin the execution evidence"
            )
        trace = _load_json_object(EVALUATION_TRACE_PATH, "NZ evaluation trace")
    if request_evidence is None:
        request_evidence = _load_json_object(
            REQUEST_TRACE_PATH, "NZ executable request evidence"
        )
    roots, canonical_requests = _derive_requested_output_roots(trace)
    _validate_request_evidence_binding(
        request_evidence,
        trace_roots=roots,
        canonical_trace_requests=canonical_requests,
    )
    return roots


def _validate_ratchet_programs(
    programs: object,
    *,
    label: str,
    require_current_program_set: bool,
) -> dict[str, dict[str, int]]:
    if not isinstance(programs, dict):
        raise ClosureError(f"{label} programs must contain an object")
    if require_current_program_set and set(programs) != set(PROGRAM_VIEWS):
        raise ClosureError("NZ closure denominator ratchet program set drifted")
    for program, row in programs.items():
        if not isinstance(program, str) or not isinstance(row, dict):
            raise ClosureError(f"{label} row {program!r} is invalid")
        for field in ("requested_output_count_min", "citation_count_min"):
            value = row.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ClosureError(f"{program}: {field} must be a non-negative integer")
    return programs


def _ratchet_from_document(
    document: dict,
    *,
    label: str,
    require_current_program_set: bool,
) -> dict[str, dict[str, int]]:
    if document.get("schema") != "axiom_oracles.nz_closure_denominator_ratchet.v1":
        raise ClosureError(f"unexpected {label} schema")
    return _validate_ratchet_programs(
        document.get("programs"),
        label=label,
        require_current_program_set=require_current_program_set,
    )


def _history_note(message: str) -> None:
    print(
        f"NZ closure NOTE: {message}; ancestor floor check failed open", file=sys.stderr
    )


def _git_history(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _ratchet_at_revision(
    revision: str,
    *,
    label: str,
    unavailable_is_note: bool,
) -> dict[str, dict[str, int]] | None:
    shown = _git_history("show", f"{revision}:{RATCHET_REPO_PATH}")
    if shown.returncode:
        if unavailable_is_note:
            _history_note(f"{label} has no readable {RATCHET_REPO_PATH}")
        return None
    try:
        document = json.loads(shown.stdout)
    except json.JSONDecodeError as exc:
        raise ClosureError(
            f"{label} denominator ratchet is invalid JSON: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise ClosureError(f"{label} denominator ratchet must contain an object")
    return _ratchet_from_document(
        document,
        label=f"{label} denominator ratchet",
        require_current_program_set=False,
    )


def _load_ancestor_denominator_ratchets() -> dict[str, dict[str, dict[str, int]]]:
    """Load merge-base and feature-history floors without requiring network access."""

    ancestors: dict[str, dict[str, dict[str, int]]] = {}

    # HEAD protects an uncommitted/staged lowering. The strict ancestor below
    # independently protects a lowering once that mutation itself is committed.
    head_ratchet = _ratchet_at_revision("HEAD", label="HEAD", unavailable_is_note=True)
    if head_ratchet is not None:
        ancestors["HEAD"] = head_ratchet

    # Walk every reachable version of the path, not only the direct parents.
    # GitHub Actions checks pull requests out at a synthetic merge commit. If
    # the PR tip itself lowers a floor, both that merge and its PR-tip parent
    # contain the lowered bytes while the older, higher floor sits one commit
    # farther back. A direct-parent-only check therefore accepts the lowering.
    # ``--full-history`` keeps both sides of merges; comparing every readable
    # version makes the effective floor the strictest value reachable from
    # HEAD, including the feature branch's pre-merge history.
    strict_history = _git_history(
        "rev-list", "--full-history", "HEAD", "--", RATCHET_REPO_PATH
    )
    if strict_history.returncode:
        _history_note(
            strict_history.stderr.strip()
            or f"reachable history for {RATCHET_REPO_PATH} is unavailable"
        )
    else:
        strict_found = False
        for revision in strict_history.stdout.splitlines():
            strict_ratchet = _ratchet_at_revision(
                revision,
                label=f"reachable HEAD history {revision}",
                unavailable_is_note=False,
            )
            if strict_ratchet is None:
                continue
            strict_found = True
            ancestors[f"reachable HEAD history {revision}"] = strict_ratchet
        if not strict_found:
            _history_note(
                f"reachable HEAD history containing {RATCHET_REPO_PATH} is unavailable"
            )

    merge_base = _git_history("merge-base", "HEAD", "origin/main")
    merge_base_revision = (
        merge_base.stdout.strip() if merge_base.returncode == 0 else ""
    )
    if not merge_base_revision:
        detail = (
            merge_base.stderr.strip() or "origin/main or its merge-base is unavailable"
        )
        _history_note(detail)
    else:
        merge_base_ratchet = _ratchet_at_revision(
            merge_base_revision,
            label=f"origin/main merge-base {merge_base_revision}",
            unavailable_is_note=True,
        )
        if merge_base_ratchet is not None:
            ancestors[f"origin/main merge-base {merge_base_revision}"] = (
                merge_base_ratchet
            )
    return ancestors


def _validate_ancestor_monotonicity(
    current: dict[str, dict[str, int]],
    *,
    ancestors: dict[str, dict[str, dict[str, int]]] | None = None,
) -> None:
    if ancestors is None:
        ancestors = _load_ancestor_denominator_ratchets()
    for label, ancestor in ancestors.items():
        ancestor = _validate_ratchet_programs(
            ancestor,
            label=label,
            require_current_program_set=False,
        )
        for program, old_row in ancestor.items():
            current_row = current.get(program)
            if current_row is None:
                raise ClosureError(
                    f"{program}: ancestor-monotone denominator RATCHET dropped the "
                    f"program present at {label}"
                )
            for field in ("requested_output_count_min", "citation_count_min"):
                old = old_row[field]
                new = current_row[field]
                if new < old:
                    raise ClosureError(
                        f"{program}: ancestor-monotone denominator RATCHET lowered "
                        f"{field} from {old} at {label} to {new}"
                    )


def load_denominator_ratchet(
    *,
    ancestor_ratchets: dict[str, dict[str, dict[str, int]]] | None = None,
) -> dict[str, dict[str, int]]:
    ratchet = _load_json_object(RATCHET_PATH, "NZ closure denominator ratchet")
    programs = _ratchet_from_document(
        ratchet,
        label="NZ closure denominator ratchet",
        require_current_program_set=True,
    )
    _validate_ancestor_monotonicity(programs, ancestors=ancestor_ratchets)
    return programs


def bootstrap_source() -> dict:
    if _git(RULESPEC_REPO, "rev-parse", RULESPEC_SHA).strip() != RULESPEC_SHA:
        raise ClosureError("pinned RuleSpec commit is unavailable")
    if _git(CORPUS_REPO, "rev-parse", CORPUS_RELEASE_REF).strip() != CORPUS_RELEASE_SHA:
        raise ClosureError("pinned corpus release ref moved or is unavailable")
    parsed_files: list[tuple[str, object]] = []
    rule_names: set[str] = set()
    for path in _git(
        RULESPEC_REPO,
        "ls-tree",
        "-r",
        "--name-only",
        RULESPEC_SHA,
        "--",
        *ROOTS,
    ).splitlines():
        raw = _git(RULESPEC_REPO, "show", f"{RULESPEC_SHA}:{path}")
        try:
            document = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ClosureError(f"{path}: invalid YAML at pinned commit: {exc}") from exc
        parsed_files.append((path, document))
        rules = document.get("rules") or [] if isinstance(document, dict) else []
        for rule in rules:
            if not isinstance(rule, dict) or not isinstance(rule.get("name"), str):
                raise ClosureError(f"{path}: rule without a string name")
            name = rule["name"]
            if name in rule_names:
                raise ClosureError(f"duplicate RuleSpec rule name {name!r}")
            rule_names.add(name)
    files: list[dict] = []
    for path, document in parsed_files:
        nodes = []
        rules = document.get("rules") or [] if isinstance(document, dict) else []
        for rule in rules:
            name = rule["name"]
            citations = sorted(_citations(rule))
            tokens = {
                token
                for formula in _formula_texts(rule)
                for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", formula)
            }
            dependencies = sorted((tokens & rule_names) - {name})
            nodes.append(
                {
                    "id": _node_id(path, name),
                    "name": name,
                    "citations": citations,
                    "citations_sha256": _list_sha256(citations),
                    "dependencies": dependencies,
                    "dependencies_sha256": _list_sha256(dependencies),
                }
            )
        files.append(
            {
                "path": path,
                "citations": sorted(_citations(document)),
                "nodes": nodes,
            }
        )
    corpus_paths: set[str] = set()
    for path in CORPUS_FILES:
        for line_number, line in enumerate(
            _git(CORPUS_REPO, "show", f"{CORPUS_RELEASE_REF}:{path}").splitlines(), 1
        ):
            try:
                row = json.loads(line)
                citation = row["citation_path"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ClosureError(
                    f"{path}:{line_number}: invalid provision row"
                ) from exc
            if citation in corpus_paths:
                raise ClosureError(f"duplicate corpus citation path {citation!r}")
            corpus_paths.add(citation)
    ledger_raw = _git(RULESPEC_REPO, "show", f"{RULESPEC_SHA}:{LEDGER_REPO_PATH}")
    ledger = yaml.safe_load(ledger_raw)
    return {
        "schema": "axiom_oracles.nz_closure_source.v2",
        "rulespec": {
            "repository": "TheAxiomFoundation/rulespec-nz",
            "commit": RULESPEC_SHA,
            "roots": list(ROOTS),
            "files": files,
        },
        "program_roots": {
            program: sorted(spec["roots"])
            for program, spec in sorted(PROGRAM_VIEWS.items())
        },
        "corpus": {
            "repository": "TheAxiomFoundation/axiom-corpus",
            "release": "nz-rulespec-2026-07-18",
            "commit": CORPUS_RELEASE_SHA,
            "provision_sources": list(CORPUS_FILES),
            "citation_paths": sorted(corpus_paths),
        },
        "pending_ledger": {
            "source": f"TheAxiomFoundation/rulespec-nz/{LEDGER_REPO_PATH}",
            "sha256": hashlib.sha256(ledger_raw.encode()).hexdigest(),
            "document": ledger,
        },
    }


def build(
    source: dict,
    *,
    requested_output_roots: dict[str, list[str]] | None = None,
    denominator_ratchet: dict[str, dict[str, int]] | None = None,
    ancestor_denominator_ratchets: dict[str, dict[str, dict[str, int]]] | None = None,
) -> dict:
    if source.get("schema") != "axiom_oracles.nz_closure_source.v2":
        raise ClosureError("unexpected NZ closure source schema")
    rulespec = source.get("rulespec") or {}
    corpus = source.get("corpus") or {}
    ledger = source.get("pending_ledger") or {}
    if (
        rulespec.get("commit") != RULESPEC_SHA
        or tuple(rulespec.get("roots") or ()) != ROOTS
    ):
        raise ClosureError("NZ closure RuleSpec pin or declared roots drifted")
    if (
        corpus.get("release") != "nz-rulespec-2026-07-18"
        or corpus.get("commit") != CORPUS_RELEASE_SHA
    ):
        raise ClosureError("NZ closure corpus release pin drifted")
    if (ledger.get("document") or {}).get("total_allowed") != 0:
        raise ClosureError("known-missing-money-atoms ceiling rose above zero")
    instrument_graph, instrument_graph_raw = _load_instrument_graph()
    instrument_decisions, instrument_decisions_raw = _load_instrument_dispositions()
    dependency_decisions, dependency_decisions_raw = _load_dependency_dispositions()
    spine_ledger, spine_ledger_raw = _load_spine_ledger()
    source_comparison, source_comparison_raw = _load_source_comparison_catalog()
    corpus_paths = corpus.get("citation_paths") or []
    if corpus_paths != sorted(set(corpus_paths)):
        raise ClosureError("corpus citation paths must be unique and sorted")
    corpus_set = set(corpus_paths)
    files = rulespec.get("files") or []
    paths = [row.get("path") for row in files if isinstance(row, dict)]
    if paths != sorted(set(paths)):
        raise ClosureError("RuleSpec file inventory must be unique and sorted")
    global_instrument_frontier, program_instrument_frontiers = (
        _build_instrument_frontiers(
            instrument_graph,
            instrument_decisions,
            rulespec_paths=set(paths),
        )
    )
    expected_program_roots = {
        program: sorted(spec["roots"])
        for program, spec in sorted(PROGRAM_VIEWS.items())
    }
    if requested_output_roots is None:
        requested_output_roots = load_requested_output_roots()
    if denominator_ratchet is None:
        denominator_ratchet = load_denominator_ratchet(
            ancestor_ratchets=ancestor_denominator_ratchets
        )
    else:
        denominator_ratchet = _validate_ratchet_programs(
            denominator_ratchet,
            label="NZ closure denominator ratchet",
            require_current_program_set=True,
        )
        _validate_ancestor_monotonicity(
            denominator_ratchet,
            ancestors=ancestor_denominator_ratchets,
        )
    if set(requested_output_roots) != set(expected_program_roots):
        raise ClosureError("NZ requested-output trace program set drifted")
    if source.get("program_roots") != requested_output_roots:
        raise ClosureError(
            "NZ program root sets are not bijective with the independent "
            "requested-output trace"
        )
    if expected_program_roots != requested_output_roots:
        raise ClosureError(
            "NZ ratified node views are not bijective with the independent "
            "requested-output trace"
        )
    for program, roots in requested_output_roots.items():
        floor = denominator_ratchet[program]["requested_output_count_min"]
        if len(roots) < floor:
            raise ClosureError(
                f"{program}: requested-output denominator RATCHET regressed "
                f"from floor {floor} to {len(roots)}"
            )
    grounding_rows = _canonical_dependency_grounding(
        dependency_decisions,
        source_comparison,
        rulespec_paths=set(paths),
    )
    dependency_closure, input_grounding = _build_dependency_closure(
        grounding_rows, instrument_decisions
    )
    try:
        spine_frontier = build_spine_frontier(source, spine_ledger=spine_ledger)
    except NZSpineError as exc:
        raise ClosureError(f"NZ spine frontier is invalid: {exc}") from exc
    nodes_by_id: dict[str, dict] = {}
    nodes_by_name: dict[str, dict] = {}
    for row in files:
        file_citations = row.get("citations")
        if not isinstance(file_citations, list) or file_citations != sorted(
            set(file_citations)
        ):
            raise ClosureError(
                f"{row.get('path')}: citations must be unique and sorted"
            )
        for node in row.get("nodes") or []:
            if not isinstance(node, dict):
                raise ClosureError(f"{row.get('path')}: invalid node entry")
            node_id = node.get("id")
            name = node.get("name")
            if not isinstance(node_id, str) or not isinstance(name, str):
                raise ClosureError(f"{row.get('path')}: node lacks id or name")
            if node_id != _node_id(row["path"], name):
                raise ClosureError(
                    f"{node_id}: node id does not match its RuleSpec path"
                )
            if node_id in nodes_by_id or name in nodes_by_name:
                raise ClosureError(f"duplicate RuleSpec node {node_id!r}")
            citations = node.get("citations")
            dependencies = node.get("dependencies")
            if not isinstance(citations, list) or citations != sorted(set(citations)):
                raise ClosureError(f"{node_id}: citations must be unique and sorted")
            if node.get("citations_sha256") != _list_sha256(citations):
                raise ClosureError(f"{node_id}: cited path was dropped or changed")
            if not set(citations).issubset(file_citations):
                raise ClosureError(
                    f"{node_id}: node citation missing from its file census"
                )
            if not isinstance(dependencies, list) or dependencies != sorted(
                set(dependencies)
            ):
                raise ClosureError(f"{node_id}: dependencies must be unique and sorted")
            if node.get("dependencies_sha256") != _list_sha256(dependencies):
                raise ClosureError(f"{node_id}: dependency edge was dropped or changed")
            nodes_by_id[node_id] = node
            nodes_by_name[name] = node
    for node_id, node in nodes_by_id.items():
        missing_dependencies = set(node["dependencies"]) - set(nodes_by_name)
        if missing_dependencies:
            raise ClosureError(
                f"{node_id}: missing dependency node(s) {sorted(missing_dependencies)}"
            )
    summaries = []
    all_pending: set[str] = set()
    for root in ROOTS:
        root_files = [
            row for row in files if str(row.get("path", "")).startswith(root + "/")
        ]
        classifications = []
        for row in root_files:
            citations = row.get("citations")
            missing = sorted(set(citations) - corpus_set)
            all_pending.update(missing)
            if missing:
                status, reason = "pending", "citation_absent_from_pinned_corpus_release"
            elif citations:
                status, reason = "encoded", "all_citations_resolve_by_exact_path"
            else:
                status, reason = (
                    "excluded",
                    "storage_or_test_file_without_corpus_citation",
                )
            classifications.append(
                {
                    "path": row["path"],
                    "status": status,
                    "reason": reason,
                    "citations": citations,
                    "missing_citations": missing,
                }
            )
        by_status = {
            name: sum(row["status"] == name for row in classifications)
            for name in ("encoded", "excluded", "pending")
        }
        summaries.append(
            {
                "root": root,
                "total_files": len(classifications),
                "by_status": by_status,
                "classifications": classifications,
            }
        )
    classified = sum(root["total_files"] for root in summaries)
    if classified != len(files):
        raise ClosureError("a RuleSpec file fell outside every declared closure root")
    program_summaries = {}
    for program, root_nodes in expected_program_roots.items():
        reached: set[str] = set()
        stack = list(root_nodes)
        while stack:
            node_id = stack.pop()
            if node_id in reached:
                continue
            node = nodes_by_id.get(node_id)
            if node is None:
                raise ClosureError(f"{program}: unknown subgraph root {node_id!r}")
            reached.add(node_id)
            stack.extend(nodes_by_name[name]["id"] for name in node["dependencies"])
        citations = sorted(
            {
                citation
                for node_id in reached
                for citation in nodes_by_id[node_id]["citations"]
            }
        )
        citation_rows = [
            {
                "citation_path": citation,
                "status": "encoded" if citation in corpus_set else "pending",
                "reason": (
                    "exact_path_present_in_pinned_corpus_release"
                    if citation in corpus_set
                    else "citation_absent_from_pinned_corpus_release"
                ),
            }
            for citation in citations
        ]
        pending = [
            row["citation_path"] for row in citation_rows if row["status"] == "pending"
        ]
        citation_floor = denominator_ratchet[program]["citation_count_min"]
        if len(citation_rows) < citation_floor:
            raise ClosureError(
                f"{program}: citation denominator RATCHET regressed "
                f"from floor {citation_floor} to {len(citation_rows)}"
            )
        instrument_frontier = program_instrument_frontiers[program]
        program_summaries[program] = {
            "closed": (
                not pending
                and instrument_frontier["complete"]
                and dependency_closure["closed"]
                and spine_frontier["complete"]
            ),
            "root_nodes": root_nodes,
            "root_node_count": len(root_nodes),
            "subgraph_node_count": len(reached),
            "citation_root_count": len(citation_rows),
            "by_status": {
                "encoded": len(citation_rows) - len(pending),
                "excluded": 0,
                "pending": len(pending),
            },
            "citations": citation_rows,
            "pending_citations": pending,
            "pending_money_atoms": 0,
            "instrument_frontier": instrument_frontier,
            "denominator_ratchet": {
                "requested_output_count_min": denominator_ratchet[program][
                    "requested_output_count_min"
                ],
                "citation_count_min": citation_floor,
            },
        }
    return {
        "schema": "axiom_oracles.nz_closure_summary.v2",
        "jurisdiction": "nz",
        "rulespec_commit": RULESPEC_SHA,
        "corpus_release": "nz-rulespec-2026-07-18",
        "corpus_commit": CORPUS_RELEASE_SHA,
        "roots": summaries,
        "pending_citations": sorted(all_pending),
        "pending_money_atoms": 0,
        "closed": (
            not all_pending
            and global_instrument_frontier["complete"]
            and dependency_closure["closed"]
            and spine_frontier["complete"]
        ),
        "programs": program_summaries,
        "generated_facts": {
            "rulespec": {
                "commit": RULESPEC_SHA,
            },
            "instrument_graph": {
                "snapshot_path": str(INSTRUMENT_GRAPH_PATH.relative_to(REPO_ROOT)),
                "snapshot_sha256": hashlib.sha256(instrument_graph_raw).hexdigest(),
                "document": instrument_graph,
            },
            "instrument_dispositions": {
                "artifact": str(INSTRUMENT_DISPOSITIONS_PATH.relative_to(REPO_ROOT)),
                "sha256": hashlib.sha256(instrument_decisions_raw).hexdigest(),
            },
            "dependency_dispositions": {
                "artifact": str(DEPENDENCY_DISPOSITIONS_PATH.relative_to(REPO_ROOT)),
                "sha256": hashlib.sha256(dependency_decisions_raw).hexdigest(),
            },
            "spine_ledger": {
                "artifact": str(SPINE_LEDGER_PATH.relative_to(REPO_ROOT)),
                "sha256": hashlib.sha256(spine_ledger_raw).hexdigest(),
                "rowset_sha256": spine_ledger.get("rowset_sha256"),
            },
            "dependency_scope_source": {
                "artifact": str(SOURCE_COMPARISON_PATH.relative_to(REPO_ROOT)),
                "sha256": hashlib.sha256(source_comparison_raw).hexdigest(),
            },
        },
        "computed": {
            "instrument_frontier": global_instrument_frontier,
            "dependency_closure": dependency_closure,
            "input_grounding": input_grounding,
            "spine_frontier": spine_frontier,
        },
        "source": {
            "artifact": str(SOURCE_PATH.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        },
        "requested_output_trace": {
            "artifact": str(EVALUATION_TRACE_PATH.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(EVALUATION_TRACE_PATH.read_bytes()).hexdigest(),
        },
        "executable_request_evidence": {
            "artifact": str(REQUEST_TRACE_PATH.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(REQUEST_TRACE_PATH.read_bytes()).hexdigest(),
        },
        "denominator_ratchet": {
            "artifact": str(RATCHET_PATH.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(RATCHET_PATH.read_bytes()).hexdigest(),
        },
    }


def validate_artifact(
    document: dict, *, repo_root: Path = REPO_ROOT
) -> ClosureValidation:
    """Pure validator used by the shared computed-certificate predicate."""

    if Path(repo_root).resolve() != REPO_ROOT.resolve():
        raise ClosureError("NZ closure must validate at the repository root")
    expected = build(load_source())
    if document != expected:
        raise ClosureError(
            "NZ closure artifact does not rederive from committed inputs"
        )
    return ClosureValidation(expected)


def verify_artifact(*, artifact_path: Path = SUMMARY_PATH) -> ClosureVerificationResult:
    """Rebuild an NZ closure artifact for the common d3 producer adapter."""

    try:
        document = _load_json_object(artifact_path, "NZ closure artifact")
        expected = build(load_source())
    except (OSError, json.JSONDecodeError, ClosureError) as exc:
        return ClosureVerificationResult(
            document=None,
            expected=None,
            errors=(str(exc),),
        )
    errors = (
        ()
        if document == expected
        else ("NZ closure artifact does not rederive from committed inputs",)
    )
    return ClosureVerificationResult(
        document=document,
        expected=expected,
        errors=errors,
    )


def _render(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    bootstrap = parser.add_mutually_exclusive_group()
    bootstrap.add_argument("--bootstrap-source", action="store_true")
    bootstrap.add_argument("--bootstrap-instrument-dispositions", action="store_true")
    bootstrap.add_argument("--bootstrap-dependency-dispositions", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.bootstrap_instrument_dispositions:
            graph, _raw = _load_instrument_graph()
            rendered = _render(bootstrap_instrument_dispositions(graph))
            if args.check:
                if (
                    not INSTRUMENT_DISPOSITIONS_PATH.exists()
                    or INSTRUMENT_DISPOSITIONS_PATH.read_text() != rendered
                ):
                    print("NZ instrument dispositions drifted", file=sys.stderr)
                    return 1
            else:
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                INSTRUMENT_DISPOSITIONS_PATH.write_text(rendered)
            return 0
        if args.bootstrap_dependency_dispositions:
            source_comparison, _raw = _load_source_comparison_catalog()
            rendered = _render(bootstrap_dependency_dispositions(source_comparison))
            if args.check:
                if (
                    not DEPENDENCY_DISPOSITIONS_PATH.exists()
                    or DEPENDENCY_DISPOSITIONS_PATH.read_text() != rendered
                ):
                    print("NZ dependency dispositions drifted", file=sys.stderr)
                    return 1
            else:
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                DEPENDENCY_DISPOSITIONS_PATH.write_text(rendered)
            return 0
        if args.bootstrap_source:
            rendered = _render(bootstrap_source())
            if args.check:
                if not SOURCE_PATH.exists() or SOURCE_PATH.read_text() != rendered:
                    print("NZ closure source snapshot drifted", file=sys.stderr)
                    return 1
            else:
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                SOURCE_PATH.write_text(rendered)
            return 0
        source = load_source()
        summary = build(source)
    except (OSError, json.JSONDecodeError, ClosureError) as exc:
        print(f"NZ closure ERROR: {exc}", file=sys.stderr)
        return 1
    rendered = _render(summary)
    if args.check:
        if not SUMMARY_PATH.exists() or SUMMARY_PATH.read_text() != rendered:
            print("NZ closure summary drifted", file=sys.stderr)
            return 1
        print("NZ closure summary up to date")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(rendered)
    print(f"wrote {SUMMARY_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
