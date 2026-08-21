#!/usr/bin/env python3
"""Build the NZ PCO XML empowering-Act reverse-index receipt.

The New Zealand Legislation API exposes XML formats for PCO-published
secondary legislation, but it does not expose an empowering-Act reverse
filter.  This producer therefore scans an exhaustive retained API download
and follows the XML's semantic ``<pursuant>`` element.  It deliberately does
not treat citations elsewhere in an instrument (history notes, amendments,
definitions, or substantive cross-references) as empowering relationships.

The resulting artifact is a source receipt, not a classification ledger.  It
reconciles the XML matches against the committed NZ instrument graph and
records how many newly captured instruments would need pending dispositions.

Default paths point at the retained 2026-06-16 API snapshot used by the NZ
lane.  They can be overridden for an exact replay elsewhere::

    python scripts/nz_pco_reverse_index.py \
      --xml-root /path/to/xml/secondary-legislation \
      --manifest /path/to/manifest-secondary_legislation.json
    python scripts/nz_pco_reverse_index.py --check
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "closure" / "nz" / "pco-empowering-act-reverse-index.json"
GRAPH_PATH = REPO_ROOT / "conformance" / "closure" / "nz-instrument-graph.json"
SNAPSHOT_ROOT = (
    Path.home()
    / "_axiom-worktrees"
    / "nz-legislation-api-downloads"
    / "2026-06-16-pco-latest"
)
XML_ROOT = SNAPSHOT_ROOT / "xml" / "secondary-legislation"
MANIFEST_PATH = SNAPSHOT_ROOT / "manifest-secondary_legislation.json"

SCHEMA = "axiom_oracles.nz_pco_empowering_act_reverse_index.v1"
SOURCE_RETRIEVED_AT = "2026-06-16"
STATUS_AS_OF = "2026-08-19"
ACCESS_OBSERVED_AT = "2026-08-21"
PCO_ELI_PREFIX = "https://www.legislation.govt.nz/secondary-legislation/pco-drafted/"


class ReverseIndexError(RuntimeError):
    """Raised when a retained source or reconciliation invariant fails."""


@dataclass(frozen=True)
class Act:
    title: str
    year: str
    number: str
    citation_path: str
    reported_count: int
    prior_titles: tuple[str, ...] = ()

    @property
    def eli(self) -> str:
        return (
            "https://www.legislation.govt.nz/act/public/"
            f"{self.year}/{int(self.number)}/en/latest/"
        )


ACTS = (
    Act(
        title="Income Tax Act 2007",
        year="2007",
        number="0097",
        citation_path="nz/statute/act/public/2007/0097",
        reported_count=202,
    ),
    Act(
        title="Social Security Act 2018",
        year="2018",
        number="0032",
        citation_path="nz/statute/act/public/2018/0032",
        reported_count=99,
    ),
    Act(
        title="Accident Compensation Act 2001",
        year="2001",
        number="0049",
        citation_path="nz/statute/act/public/2001/0049",
        reported_count=136,
        prior_titles=("Injury Prevention, Rehabilitation, and Compensation Act 2001",),
    ),
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _element_text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())


def _first_text(root: ET.Element, local_name: str) -> str:
    for element in root.iter():
        if _local_name(element.tag) == local_name:
            value = _element_text(element)
            if value:
                return value
    return ""


def _pursuant_text(root: ET.Element) -> str:
    return " ".join(
        _element_text(element)
        for element in root.iter()
        if _local_name(element.tag) == "pursuant"
    )


def _xml_date(value: str | None) -> dt.date | None:
    if not value or value == "nulldate":
        return None
    match = re.match(r"\d{4}-\d{2}-\d{2}", value)
    if match is None:
        raise ReverseIndexError(f"unsupported PCO XML date {value!r}")
    return dt.date.fromisoformat(match.group())


def _instrument_graph_row(
    root: ET.Element,
    *,
    act: Act,
    year: str,
    number: str,
) -> dict[str, Any]:
    """Derive the exact graph row used by the NZ offline capture."""

    date_document = (
        root.get("date.signed")
        or root.get("date.gazetted")
        or root.get("date.first.valid")
        or root.get("date.as.at")
        or ""
    )
    first_valid = _xml_date(root.get("date.first.valid"))
    terminated = _xml_date(root.get("date.terminated"))
    status_as_of = dt.date.fromisoformat(STATUS_AS_OF)
    in_force = (first_valid is None or first_valid <= status_as_of) and (
        terminated is None or status_as_of < terminated
    )
    instrument_type = (root.get("sr.type") or _local_name(root.tag)).strip()
    series = "SL" if int(year) >= 2022 else "LI" if int(year) >= 2012 else "SR"
    return {
        "eli": (
            "https://www.legislation.govt.nz/secondary-legislation/"
            f"pco-drafted/{year}/{int(number)}/en/latest/"
        ),
        "relation": "basis_for",
        "date_document": date_document,
        "type_document": instrument_type.upper().replace(" ", "_"),
        "in_force": in_force,
        "title": _first_text(root, "title"),
        "title_short": f"{series} {year}/{int(number)}",
        "act_eli": act.eli,
        "act_citation_path": act.citation_path,
        "empowering_provisions": _pursuant_text(root),
    }


def _work_parts(path: Path) -> tuple[str, str]:
    parts = path.parts
    try:
        marker = parts.index("pco-drafted")
        year = parts[marker + 1]
        number = parts[marker + 2]
    except (ValueError, IndexError) as exc:
        raise ReverseIndexError(f"cannot derive PCO work identity from {path}") from exc
    if not re.fullmatch(r"\d{4}", year) or not re.fullmatch(r"\d+", number):
        raise ReverseIndexError(f"invalid PCO work identity in {path}")
    return year, number


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReverseIndexError(f"cannot read {label} {path}: {exc}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReverseIndexError(f"invalid JSON in {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReverseIndexError(f"{label} {path} must contain a JSON object")
    return value, raw


def _load_manifest(
    path: Path,
) -> tuple[dict[str, Any], bytes, dict[str, dict[str, Any]]]:
    manifest, raw = _load_json(path, "PCO manifest")
    discovered = manifest.get("discovered_count")
    downloaded = manifest.get("downloaded_count")
    failed = manifest.get("failed_count")
    failures = manifest.get("failures")
    sources = manifest.get("sources")
    if (
        not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (discovered, downloaded, failed)
        )
        or discovered != downloaded + failed
        or not isinstance(failures, list)
        or len(failures) != failed
        or not isinstance(sources, list)
        or len(sources) != discovered
    ):
        raise ReverseIndexError("PCO manifest counts and row arrays do not reconcile")

    by_relative_path: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise ReverseIndexError("PCO manifest source rows must be objects")
        relative_path = source.get("relative_path")
        if relative_path is None:
            # The one failed download has no retained relative path.
            continue
        if not isinstance(relative_path, str) or not relative_path:
            raise ReverseIndexError("PCO manifest relative_path must be a string")
        if relative_path in by_relative_path:
            raise ReverseIndexError(f"duplicate manifest relative_path {relative_path}")
        by_relative_path[relative_path] = source
    # ``sources`` describes all discovered works, including a failed work whose
    # intended relative path is still present.  The filesystem count is checked
    # against ``downloaded_count`` after the scan.
    if len(by_relative_path) != discovered:
        raise ReverseIndexError("PCO manifest source paths are not exhaustive")
    return manifest, raw, by_relative_path


def _manifest_source_for(
    path: Path,
    *,
    xml_root: Path,
    manifest_sources: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    relative_path = path.relative_to(xml_root).as_posix()
    manifest_relative_path = f"secondary-legislation/{relative_path}"
    source = manifest_sources.get(manifest_relative_path)
    if source is None:
        raise ReverseIndexError(
            f"{relative_path}: XML file has no matching retained manifest source"
        )
    return relative_path, source


def _matched_act(pursuant: str, path: Path) -> tuple[Act, str] | None:
    matches: list[tuple[Act, str]] = []
    for act in ACTS:
        matched_titles = [
            title for title in (act.title, *act.prior_titles) if title in pursuant
        ]
        if matched_titles:
            matches.append((act, matched_titles[0]))
    if len(matches) > 1:
        titles = ", ".join(match[0].title for match in matches)
        raise ReverseIndexError(f"{path}: <pursuant> matches multiple Acts: {titles}")
    return matches[0] if matches else None


def _scan_xml(
    xml_root: Path,
    manifest_sources: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    if not xml_root.is_dir():
        raise ReverseIndexError(f"PCO XML root does not exist: {xml_root}")
    paths = sorted(xml_root.rglob("*.xml"))
    if not paths:
        raise ReverseIndexError(f"PCO XML root contains no XML files: {xml_root}")

    rows: list[dict[str, Any]] = []
    seen_elis: set[str] = set()
    for path in paths:
        raw = path.read_bytes()
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise ReverseIndexError(f"invalid PCO XML {path}: {exc}") from exc
        relative_path, source = _manifest_source_for(
            path, xml_root=xml_root, manifest_sources=manifest_sources
        )
        pursuant = _pursuant_text(root)
        match = _matched_act(pursuant, path)
        if match is None:
            continue
        act, matched_title = match
        year, number = _work_parts(path)
        instrument_graph_row = _instrument_graph_row(
            root,
            act=act,
            year=year,
            number=number,
        )
        eli = instrument_graph_row["eli"]
        xml_url = source.get("xml_url")
        work_id = source.get("work_id")
        version_id = source.get("version_id")
        metadata = source.get("metadata")
        if (
            not isinstance(xml_url, str)
            or not isinstance(work_id, str)
            or not isinstance(version_id, str)
            or not isinstance(metadata, dict)
            or metadata.get("publisher") != "Parliamentary Counsel Office"
        ):
            raise ReverseIndexError(
                f"{relative_path}: incomplete or non-PCO manifest provenance"
            )
        if xml_url != eli.rstrip("/") + ".xml":
            raise ReverseIndexError(
                f"{relative_path}: manifest XML URL does not match derived ELI"
            )
        if eli in seen_elis:
            raise ReverseIndexError(f"duplicate matched instrument ELI {eli}")
        seen_elis.add(eli)
        rows.append(
            {
                "act_title": act.title,
                "act_eli": act.eli,
                "act_citation_path": act.citation_path,
                "matched_empowering_act_title": matched_title,
                "eli": eli,
                "title": _first_text(root, "title"),
                "empowering_text": pursuant,
                "instrument_graph_row": instrument_graph_row,
                "work_id": work_id,
                "version_id": version_id,
                "source_url": xml_url,
                "source_relative_path": relative_path,
                "source_sha256": _sha256(raw),
            }
        )
    rows.sort(key=lambda row: (row["act_citation_path"], row["eli"]))
    return rows, len(paths)


def _official_graph_rows(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    instruments = graph.get("instruments")
    if not isinstance(instruments, list):
        raise ReverseIndexError("instrument graph instruments must be an array")
    result: dict[str, dict[str, Any]] = {}
    for row in instruments:
        if not isinstance(row, dict):
            raise ReverseIndexError("instrument graph rows must be objects")
        eli = row.get("eli")
        if not isinstance(eli, str) or not eli.startswith(PCO_ELI_PREFIX):
            continue
        if eli in result:
            raise ReverseIndexError(f"duplicate PCO graph ELI {eli}")
        result[eli] = row
    return result


def _graph_receipts(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    receipts = graph.get("retrieval_receipts")
    if not isinstance(receipts, list):
        raise ReverseIndexError("instrument graph retrieval_receipts must be an array")
    result: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise ReverseIndexError("instrument graph receipts must be objects")
        citation = receipt.get("act_citation_path")
        if not isinstance(citation, str) or citation in result:
            raise ReverseIndexError("instrument graph receipt Act keys are invalid")
        result[citation] = receipt
    return result


def _reconcile(
    rows: list[dict[str, Any]], graph: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
    graph_rows = _official_graph_rows(graph)
    receipts = _graph_receipts(graph)
    reverse_rows = {row["eli"]: row for row in rows}

    for eli in sorted(set(reverse_rows) & set(graph_rows)):
        reverse = reverse_rows[eli]
        committed = graph_rows[eli]
        comparisons = reverse["instrument_graph_row"]
        for field, expected in comparisons.items():
            if committed.get(field) != expected:
                raise ReverseIndexError(
                    f"{eli}: reverse-index {field} disagrees with instrument graph"
                )

    by_act: list[dict[str, Any]] = []
    totals = {
        "reported_listing_rows": 0,
        "bulk_xml_matches": 0,
        "already_in_instrument_graph": 0,
        "newly_resolved": 0,
        "pending_merges": 0,
        "remaining_capture_gap": 0,
    }
    pending_disposition_rows: list[dict[str, Any]] = []
    for act in ACTS:
        act_rows = [
            row for row in rows if row["act_citation_path"] == act.citation_path
        ]
        already = sum(row["eli"] in graph_rows for row in act_rows)
        new = len(act_rows) - already
        remaining = act.reported_count - len(act_rows)
        if remaining < 0:
            raise ReverseIndexError(
                f"{act.title}: XML match count exceeds reported listing count"
            )
        receipt = receipts.get(act.citation_path)
        if receipt is None:
            raise ReverseIndexError(f"{act.title}: missing instrument graph receipt")
        graph_act_count = sum(
            row.get("act_citation_path") == act.citation_path
            for row in graph_rows.values()
        )
        expected_receipt = {
            "reported_count": act.reported_count,
            "captured_count": graph_act_count,
            "unresolved_count": act.reported_count - graph_act_count,
        }
        for field, expected in expected_receipt.items():
            if receipt.get(field) != expected:
                raise ReverseIndexError(
                    f"{act.title}: graph receipt {field} does not equal {expected}"
                )
        row = {
            "act_title": act.title,
            "act_eli": act.eli,
            "act_citation_path": act.citation_path,
            "reported_listing_rows": act.reported_count,
            "bulk_xml_matches": len(act_rows),
            "already_in_instrument_graph": already,
            "newly_resolved": new,
            # New captures are inputs to B2 and therefore would be merged as
            # pending, never classified by this producer.
            "pending_merges": new,
            "remaining_capture_gap": remaining,
        }
        by_act.append(row)
        for field in totals:
            totals[field] += row[field]
        pending_disposition_rows.extend(
            {
                "status": "pending",
                "classification_owner": "B2",
                "instrument_graph_row": reverse["instrument_graph_row"],
                "source_receipt": {
                    key: reverse[key]
                    for key in (
                        "source_relative_path",
                        "source_sha256",
                        "source_url",
                        "version_id",
                        "work_id",
                    )
                },
            }
            for reverse in act_rows
            if reverse["eli"] not in graph_rows
        )

    unmatched_graph = sorted(set(graph_rows) - set(reverse_rows))
    if unmatched_graph:
        raise ReverseIndexError(
            "committed PCO graph rows are absent from the authoritative reverse index: "
            + ", ".join(unmatched_graph)
        )
    pending_disposition_rows.sort(
        key=lambda row: str(row["instrument_graph_row"]["eli"])
    )
    if len(pending_disposition_rows) != totals["pending_merges"]:
        raise ReverseIndexError("pending merge rows do not reconcile to counts")
    return by_act, totals, pending_disposition_rows


def build_artifact(
    *, xml_root: Path, manifest_path: Path, graph_path: Path
) -> dict[str, Any]:
    manifest, manifest_raw, manifest_sources = _load_manifest(manifest_path)
    graph, graph_raw = _load_json(graph_path, "instrument graph")
    rows, xml_files_scanned = _scan_xml(xml_root, manifest_sources)
    if xml_files_scanned != manifest["downloaded_count"]:
        raise ReverseIndexError(
            "retained XML file count does not equal manifest downloaded_count"
        )
    by_act, totals, pending_disposition_rows = _reconcile(rows, graph)
    failed_work_ids = sorted(
        str(row["work_id"])
        for row in manifest["failures"]
        if isinstance(row, dict) and row.get("work_id")
    )
    if len(failed_work_ids) != manifest["failed_count"]:
        raise ReverseIndexError("manifest failures do not all identify a work_id")

    return {
        "schema": SCHEMA,
        "purpose": (
            "Authoritative PCO XML instrument-to-empowering-Act reverse index for "
            "the three NZ certification Acts; source receipt only, with any newly "
            "resolved rows reserved as pending for B2 disposition."
        ),
        "source": {
            "data_service": "New Zealand Legislation API v0",
            "publisher": "New Zealand Parliamentary Counsel Office",
            "works_endpoint_used_for_retained_snapshot": (
                "https://api.legislation.govt.nz/v0/works/"
            ),
            "per_work_xml_endpoint_pattern": (
                "https://www.legislation.govt.nz/secondary-legislation/"
                "pco-drafted/{year}/{number}/en/latest.xml"
            ),
            "api_documentation_url": "https://api.legislation.govt.nz/docs/",
            "bulk_catalogue_url": (
                "https://catalogue.data.govt.nz/dataset/new-zealand-legislation"
            ),
            "xml_documentation_url": (
                "https://www.legislation.govt.nz/learn-more/legislation-data/xml-data/"
            ),
            "classic_site_scope_documentation_url": (
                "https://www.legislation.govt.nz/howitworks.aspx"
            ),
            "snapshot_id": "2026-06-16-pco-latest",
            "source_retrieved_at": SOURCE_RETRIEVED_AT,
            "status_evaluated_as_of": STATUS_AS_OF,
            "publisher_scope": "Parliamentary Counsel Office",
            "format_scope": "official XML",
            "match_rule": (
                "Normalize and concatenate XML <pursuant> text, then match an exact "
                "empowering-Act title substring. Accident Compensation Act rows also "
                "accept its former title, Injury Prevention, Rehabilitation, and "
                "Compensation Act 2001. Text outside <pursuant> is never an edge."
            ),
            "manifest_name": manifest_path.name,
            "manifest_sha256": _sha256(manifest_raw),
            "manifest_discovered_count": manifest["discovered_count"],
            "manifest_downloaded_count": manifest["downloaded_count"],
            "manifest_failed_count": manifest["failed_count"],
            "manifest_failed_work_ids": failed_work_ids,
            "instrument_graph_path": graph_path.relative_to(REPO_ROOT).as_posix()
            if graph_path.is_relative_to(REPO_ROOT)
            else graph_path.name,
            "instrument_graph_sha256": _sha256(graph_raw),
        },
        "access_limitations": {
            "observed_at": ACCESS_OBSERVED_AT,
            "api_authentication": (
                "The API v0 works endpoint requires X-Api-Key. No "
                "NZ_LEGISLATION_API_KEY was available in this run, so the retained "
                "official snapshot was replayed instead of refreshing the API."
            ),
            "reverse_filter": (
                "The documented works endpoint has no empowering-Act reverse filter."
            ),
            "agency_drafted_formats": (
                "The API documentation says agency-drafted records can link to agency "
                "sites and have varying HTML/PDF formats; authoritative XML is not "
                "guaranteed for that remainder."
            ),
            "client_rendered_act_tabs": (
                "Not accessed: the brief forbids using the client-rendered Act tabs "
                "or a human-verification flow."
            ),
            "bulk_catalogue_wall": (
                "The official catalogue page exposed an Incapsula challenge in this "
                "environment; the challenge was not bypassed."
            ),
            "human_verification_wall": (
                "An official API-announcement/news path presented a JavaScript/robot "
                "verification wall; that path was stopped and was not used as evidence."
            ),
            "multi_act_representation": (
                "The retained snapshot contains no instrument whose <pursuant> text "
                "matches more than one of the three target Acts. A future multi-target "
                "match fails closed because the current graph has one scalar Act owner; "
                "it is not silently assigned to either Act."
            ),
            "predecessor_acts": (
                "No predecessor-to-successor inference was made for instruments "
                "whose <pursuant> text names an earlier Income Tax, Social Security, "
                "accident insurance, or compensation Act. Such an edge requires an "
                "authoritative continuation or savings rule; title similarity alone "
                "does not place it under a current Act."
            ),
            "scope_consequence": (
                "This PCO-publisher XML reverse index cannot honestly invent the "
                "agency-published, predecessor-Act, or otherwise unresolved listing "
                "rows."
            ),
        },
        "counts": {
            "xml_files_scanned": xml_files_scanned,
            **totals,
        },
        "by_act": by_act,
        "pending_disposition_rows": pending_disposition_rows,
        "rows": rows,
    }


def serialize(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=1) + "\n").encode()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xml-root",
        type=Path,
        default=Path(os.environ.get("NZ_PCO_BULK_XML_ROOT", XML_ROOT)),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(os.environ.get("NZ_PCO_BULK_MANIFEST", MANIFEST_PATH)),
    )
    parser.add_argument("--graph", type=Path, default=GRAPH_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail unless exact committed bytes rederive",
    )
    args = parser.parse_args(argv)

    try:
        rendered = serialize(
            build_artifact(
                xml_root=args.xml_root,
                manifest_path=args.manifest,
                graph_path=args.graph,
            )
        )
    except ReverseIndexError as exc:
        print(f"NZ PCO reverse index: {exc}", file=sys.stderr)
        return 1

    if args.check:
        try:
            committed = args.output.read_bytes()
        except OSError as exc:
            print(
                f"NZ PCO reverse index: cannot read {args.output}: {exc}",
                file=sys.stderr,
            )
            return 1
        if committed != rendered:
            print(
                f"NZ PCO reverse index drift: regenerate {args.output}", file=sys.stderr
            )
            return 1
        print("NZ PCO reverse index current")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rendered)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
