#!/usr/bin/env python3
"""Capture the NZ subordinate-instrument frontier used by NZ closure.

This is the NZ analogue of ``refresh_instrument_graph.py``.  It is the only
step in the NZ instrument lane that is allowed to use the network.  The
closure producer reads only the committed JSON snapshot and binds its exact
bytes.

The live capture deliberately refuses a partially rendered Act page.  The
redeveloped NZ Legislation site exposes agency-published instruments in a
client-rendered "Secondary legislation" tab; a capture is usable only when
the number of unique rows equals the tab's advertised total.  The classic
site is retained as a PCO-only cross-check and is not treated as the complete
frontier.

An ``--offline-pco-root`` mode exists solely to make the current constrained
capture and parser reproducible.  It reads an exhaustive official PCO XML
download, marks every Act receipt incomplete against the live tab count, and
therefore can never make an NZ certificate closed.

Usage::

    uv run python scripts/refresh_nz_instrument_graph.py
    uv run python scripts/refresh_nz_instrument_graph.py --diff
    uv run python scripts/refresh_nz_instrument_graph.py \
      --offline-pco-root /path/to/xml/secondary-legislation \
      --offline-manifest /path/to/manifest-secondary_legislation.json \
      --offline-source-retrieved-at 2026-06-16 \
      --allow-incomplete
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import requests


REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "conformance" / "closure" / "nz-instrument-graph.json"
SCHEMA = "axiom_oracles.closure.instrument_graph.v1"
CAPTURE_DATE = "2026-08-19"
SCHEMA_COMPATIBILITY_NOTE = (
    "NZ needs one graph for three empowering Acts and program-scoped decisions. "
    "instrument_graph.v1 on d3/instrument-frontier is single-Act (scalar act_eli "
    "and act_citation_path, exact seven-key rows); this document preserves that "
    "schema identifier while using Act arrays, per-row Act identity, and retrieval "
    "receipts as the multi-Act extension requested by Brief F1. Common-schema "
    "adjudication is still required before treating the extension as portable. "
    "The v1 unique-ELI/one-Act shape also cannot express guidance bearing on more "
    "than one empowering Act; each such row has one disclosed primary owner until "
    "that representation is adjudicated."
)


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

    @property
    def listing_url(self) -> str:
        return self.eli

    @property
    def classic_listing_url(self) -> str:
        return (
            "https://classic.legislation.govt.nz/act/public/"
            f"{self.year}/{self.number}/latest/secondary.aspx"
            "?sds=aa&sdr=1&sda=1"
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
        prior_titles=(
            "Injury Prevention, Rehabilitation, and Compensation Act 2001",
        ),
    ),
)


# These are supplemental candidate-set rows, not a claim that every web page
# is legislation.  ``relation=bears_on`` and ``type_document`` make the
# distinction reviewable.  The dispositions ledger decides whether each row
# is encoded, classified, excluded, or pending for each certified program.
SUPPLEMENTAL_INSTRUMENTS: tuple[dict[str, Any], ...] = (
    {
        "eli": "https://www.ird.govt.nz/en/income-tax/income-tax-for-individuals/acc-clients-and-carers/acc-earners-levy-rates",
        "title": "ACC earners' levy rates",
        "title_short": "IRD ACC earners' levy rates",
        "type_document": "GUIDANCE",
        "date_document": "2025-03-06",
        "act": "Accident Compensation Act 2001",
    },
    {
        "eli": "https://www.workandincome.govt.nz/products/benefit-rates/benefit-rates-april-2026.html",
        "title": "Benefit rates at 1 April 2026",
        "title_short": "W&I benefit rates 2026-04-01",
        "type_document": "GUIDANCE",
        "date_document": "2026-07-13",
        "act": "Social Security Act 2018",
    },
    {
        "eli": "https://www.ird.govt.nz/working-for-families/types/family-tax-credit",
        "title": "Family tax credit",
        "title_short": "IRD family tax credit",
        "type_document": "GUIDANCE",
        "date_document": "2026-02-25",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.ird.govt.nz/working-for-families/types/in-work-tax-credit",
        "title": "In-work tax credit",
        "title_short": "IRD in-work tax credit",
        "type_document": "GUIDANCE",
        "date_document": "2026-03-24",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.ird.govt.nz/best-start",
        "title": "Best Start tax credit",
        "title_short": "IRD Best Start",
        "type_document": "GUIDANCE",
        "date_document": "2026-02-25",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.ird.govt.nz/working-for-families/types/minimum-family-tax-credit",
        "title": "Minimum family tax credit",
        "title_short": "IRD minimum family tax credit",
        "type_document": "GUIDANCE",
        "date_document": "2026-02-25",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.ird.govt.nz/in-work-tax-credit-increase",
        "title": "In-work tax credit increase",
        "title_short": "IRD IWTC temporary increase",
        "type_document": "GUIDANCE",
        "date_document": "2026-03-24",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.taxtechnical.ird.govt.nz/interpretation-statements/2026/is-26-12",
        "title": "Working for Families tax credits and family scheme income",
        "title_short": "IS 26/12",
        "type_document": "INTERPRETATION_STATEMENT",
        "date_document": "2026-06-18",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.taxtechnical.ird.govt.nz/fact-sheets/2026/is-26-12-fs-1",
        "title": "Working for Families tax credits and family scheme income fact sheet",
        "title_short": "IS 26/12 FS 1",
        "type_document": "FACT_SHEET",
        "date_document": "2026-06-18",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.taxtechnical.ird.govt.nz/determinations/emergency-events/2026/det-26-01",
        "title": "Declaration that the January 2026 severe weather event is an emergency event for the purposes of family scheme income",
        "title_short": "DET 26/01",
        "type_document": "DETERMINATION",
        "date_document": "2026-02-03",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.taxtechnical.ird.govt.nz/determinations/emergency-events/2026/det-26-02",
        "title": "Declaration that the February 2026 severe weather event is an emergency event for the purposes of family scheme income",
        "title_short": "DET 26/02",
        "type_document": "DETERMINATION",
        "date_document": "2026-02-19",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.taxtechnical.ird.govt.nz/determinations/emergency-events/2026/det-26-03",
        "title": "Declaration that the April 2026 Wellington severe weather event is an emergency event for the purposes of family scheme income",
        "title_short": "DET 26/03",
        "type_document": "DETERMINATION",
        "date_document": "2026-04-28",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.taxtechnical.ird.govt.nz/determinations/emergency-events/2023/ee-23-01",
        "title": "Declaration of the January 2023 flood events and Cyclone Gabrielle as emergency events for family scheme income",
        "title_short": "EE 23/01",
        "type_document": "DETERMINATION",
        "date_document": "2023-02-27",
        "in_force": False,
        "application_end": "2023-08-31",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.taxtechnical.ird.govt.nz/determinations/emergency-events/det-ee-1101-declaration-of-the-canterbury-earthquake-of-4-september-2010-as-an-emergency-event-for-t",
        "title": "Declaration of the Canterbury earthquake of 4 September 2010 as an emergency event for family scheme income",
        "title_short": "DET EE-11/01",
        "type_document": "DETERMINATION",
        "date_document": "2011-05-26",
        "in_force": False,
        "application_end": "2011-09-03",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.taxtechnical.ird.govt.nz/determinations/emergency-events/det-ee-1102-declaration-of-the-canterbury-earthquake-of-22-february-2011-as-an-emergency-event-for-t",
        "title": "Declaration of the Canterbury earthquake of 22 February 2011 as an emergency event for family scheme income",
        "title_short": "DET EE-11/02",
        "type_document": "DETERMINATION",
        "date_document": "2011-05-26",
        "in_force": False,
        "application_end": "2012-02-21",
        "act": "Income Tax Act 2007",
    },
    {
        "eli": "https://www.ird.govt.nz/rwt-rate",
        "title": "Inland Revenue — Resident withholding tax (RWT) rates",
        "title_short": "nz-ird-rwt-rates",
        "type_document": "CORPUS_GUIDANCE",
        "date_document": "2026-07-25",
        "act": "Income Tax Act 2007",
        "corpus_citation_path": "nz/guidance/ird/rwt-rates",
    },
    {
        "eli": "https://www.ird.govt.nz/deductions-from-salary-and-wages",
        "title": "Inland Revenue — Deductions from salary and wages",
        "title_short": "nz-ird-paye-deduction-tables",
        "type_document": "CORPUS_GUIDANCE",
        "date_document": "2026-07-25",
        # The corpus inventory says this page covers PAYE and ACC earners'
        # levy.  The certified income-tax calculation does not claim PAYE
        # withholding, while the ACC program does consume the levy surface,
        # so the single-owner v1 extension assigns it to the ACC Act.  The
        # schema note records the unresolved multi-Act ownership limitation.
        "act": "Accident Compensation Act 2001",
        "corpus_citation_path": "nz/guidance/ird/paye-deduction-tables",
    },
    {
        "eli": "https://www.acc.co.nz/im-injured/financial-support/weekly-compensation",
        "title": "ACC — Weekly compensation",
        "title_short": "nz-acc-weekly-compensation",
        "type_document": "CORPUS_GUIDANCE",
        "date_document": "2026-07-25",
        "act": "Accident Compensation Act 2001",
        "corpus_citation_path": "nz/guidance/acc/weekly-compensation",
    },
    {
        "eli": "https://www.acc.co.nz/im-injured/financial-support/weekly-compensation/weekly-compensation-for-employees",
        "title": "ACC — Weekly compensation for employees (including loss of potential earnings)",
        "title_short": "nz-acc-weekly-compensation-employees",
        "type_document": "CORPUS_GUIDANCE",
        "date_document": "2026-07-25",
        "act": "Accident Compensation Act 2001",
        "corpus_citation_path": "nz/guidance/acc/weekly-compensation-for-employees",
    },
    {
        "eli": "https://www.acc.co.nz/newsroom/stories/changes-to-client-payments-from-1-april-2025",
        "title": "ACC — Changes to client payments from 1 April 2025",
        "title_short": "nz-acc-client-payment-rates-2025-04",
        "type_document": "CORPUS_GUIDANCE",
        "date_document": "2025-03-27",
        "act": "Accident Compensation Act 2001",
        "corpus_citation_path": "nz/guidance/acc/client-payment-rates-2025-04",
        "corpus_commit": "e66f04b718468b7521f4e05542b789c2df9a1177",
    },
    {
        "eli": "https://www.acc.co.nz/newsroom/stories/changes-to-client-payments-from-1-april-2026",
        "title": "ACC — Changes to client payments from 1 April 2026",
        "title_short": "nz-acc-client-payment-rates-2026-04",
        "type_document": "CORPUS_GUIDANCE",
        "date_document": "2026-03-31",
        "act": "Accident Compensation Act 2001",
        "corpus_citation_path": "nz/guidance/acc/client-payment-rates-2026-04",
    },
    {
        "eli": "https://www.acc.co.nz/newsroom/stories/changes-to-acc-client-payments-from-1-july-2026",
        "title": "ACC — Changes to ACC client payments from 1 July 2026",
        "title_short": "nz-acc-client-payment-rates-2026-07",
        "type_document": "CORPUS_GUIDANCE",
        "date_document": "2026-06-11",
        "act": "Accident Compensation Act 2001",
        "corpus_citation_path": "nz/guidance/acc/client-payment-rates-2026-07",
    },
)


_CORPUS_GUIDANCE_COMMIT = "e66f04b718468b7521f4e05542b789c2df9a1177"
_CORPUS_GUIDANCE_INVENTORY = (
    "data/corpus/inventory/nz/guidance/2026-07-25-rulespec-nz-guidance.json"
)
_CORPUS_GUIDANCE_INVENTORY_SHA256 = (
    "8990f85617ce183e01f833d9ad2a65614d1e55a992fa812563c2a0b769a9ffbf"
)
_CORPUS_SOURCE_SHA256 = {
    "nz/guidance/ird/rwt-rates": (
        "cd7968f72312e8cc8bd367cc96f299b6c6b6ea0b8dff38f570c6a260568cf641"
    ),
    "nz/guidance/ird/paye-deduction-tables": (
        "15a48f660429901aaf2248f157aa00bba97be20006ca98f5ee2f3ee80a39d450"
    ),
    "nz/guidance/acc/weekly-compensation": (
        "e94af6ec541b3125abb0d8d04352de4b1d23caee149eeabb5b851ae1e4d202d9"
    ),
    "nz/guidance/acc/weekly-compensation-for-employees": (
        "c194e748fba73e6643530af887495e899fc49cc6cc9cff001759425d90dfe904"
    ),
    "nz/guidance/acc/client-payment-rates-2026-04": (
        "1a1da3d13d67737c9cce6f67297d565480c9c842bf05c5158d06c933c01373ac"
    ),
    "nz/guidance/acc/client-payment-rates-2026-07": (
        "bccf7051e55cc86b7fe3a935271e75f5c208c9ec6b4db248d6fbfa77744aea7b"
    ),
}
_APRIL_2025_MANIFEST = "manifests/nz-agency-guidance-documents.yaml"
_APRIL_2025_MANIFEST_SHA256 = (
    "c3fd818276919befcc5d81f81ee72a402e2361937eb19a7356fb9552fc338559"
)


class CaptureError(RuntimeError):
    """Raised when an authoritative capture is incomplete or malformed."""


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.anchors.append((self._href, " ".join(self._text).strip()))
            self._href = None
            self._text = []


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def _work_parts(path: Path) -> tuple[str, str]:
    parts = path.parts
    try:
        marker = parts.index("pco-drafted")
        return parts[marker + 1], parts[marker + 2]
    except (ValueError, IndexError) as exc:
        raise CaptureError(f"cannot derive PCO work id from {path}") from exc


def _instrument_type(root: ET.Element) -> str:
    value = (root.get("sr.type") or _local_name(root.tag)).strip()
    return value.upper().replace(" ", "_")


def _xml_date(value: str | None) -> dt.date | None:
    if not value or value == "nulldate":
        return None
    match = re.match(r"\d{4}-\d{2}-\d{2}", value)
    if match is None:
        raise CaptureError(f"unsupported PCO XML date {value!r}")
    return dt.date.fromisoformat(match.group())


def _offline_row(
    path: Path, root: ET.Element, act: Act, *, status_as_of: dt.date
) -> dict[str, Any]:
    year, number = _work_parts(path)
    date_document = (
        root.get("date.signed")
        or root.get("date.gazetted")
        or root.get("date.first.valid")
        or root.get("date.as.at")
        or ""
    )
    first_valid = _xml_date(root.get("date.first.valid"))
    terminated = _xml_date(root.get("date.terminated"))
    in_force = (first_valid is None or first_valid <= status_as_of) and (
        terminated is None or status_as_of < terminated
    )
    title = _first_text(root, "title")
    series = "SL" if int(year) >= 2022 else "LI" if int(year) >= 2012 else "SR"
    return {
        "eli": (
            "https://www.legislation.govt.nz/secondary-legislation/"
            f"pco-drafted/{year}/{int(number)}/en/latest/"
        ),
        "relation": "basis_for",
        "date_document": date_document,
        "type_document": _instrument_type(root),
        "in_force": in_force,
        "title": title,
        "title_short": f"{series} {year}/{int(number)}",
        "act_eli": act.eli,
        "act_citation_path": act.citation_path,
        "empowering_provisions": _pursuant_text(root),
    }


def _offline_capture(
    xml_root: Path,
    manifest_path: Path | None,
    *,
    source_retrieved_at: dt.date,
    status_as_of: dt.date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not xml_root.is_dir():
        raise CaptureError(f"offline PCO XML root does not exist: {xml_root}")
    rows: list[dict[str, Any]] = []
    counts = {act.title: 0 for act in ACTS}
    for path in sorted(xml_root.rglob("*.xml")):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise CaptureError(f"invalid PCO XML {path}: {exc}") from exc
        pursuant = _pursuant_text(root)
        matched = [
            act
            for act in ACTS
            if any(
                title in pursuant for title in (act.title, *act.prior_titles)
            )
        ]
        if len(matched) > 1:
            raise CaptureError(f"{path} matches multiple empowering Acts")
        if not matched:
            continue
        act = matched[0]
        rows.append(_offline_row(path, root, act, status_as_of=status_as_of))
        counts[act.title] += 1
    manifest_receipt: dict[str, Any] = {
        "method": "official PCO API v0 XML replay filtered by pursuant text",
        "source_retrieved_at": source_retrieved_at.isoformat(),
        "status_evaluated_as_of": status_as_of.isoformat(),
        "complete": False,
    }
    if manifest_path is not None:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
        if not isinstance(manifest, dict):
            raise CaptureError("offline PCO manifest must contain an object")
        discovered = manifest.get("discovered_count")
        downloaded = manifest.get("downloaded_count")
        failed = manifest.get("failed_count")
        failures = manifest.get("failures")
        if (
            not all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in (discovered, downloaded, failed)
            )
            or discovered != downloaded + failed
            or not isinstance(failures, list)
            or len(failures) != failed
        ):
            raise CaptureError("offline PCO manifest counts do not reconcile")
        failed_work_ids = sorted(
            str(row.get("work_id"))
            for row in failures
            if isinstance(row, dict) and row.get("work_id")
        )
        manifest_receipt.update(
            {
                "manifest_sha256": _sha256(raw),
                "manifest_name": manifest_path.name,
                "manifest_discovered_count": discovered,
                "manifest_downloaded_count": downloaded,
                "manifest_failed_count": failed,
                "manifest_failed_work_ids": failed_work_ids,
            }
        )
    receipts = []
    for act in ACTS:
        captured = counts[act.title]
        receipts.append(
            {
                "act_eli": act.eli,
                "act_citation_path": act.citation_path,
                "listing_url": act.listing_url,
                "classic_cross_check_url": act.classic_listing_url,
                "reported_count": act.reported_count,
                "captured_count": captured,
                "unresolved_count": act.reported_count - captured,
                **manifest_receipt,
            }
        )
    return rows, receipts


def _extract_instrument_links(raw: bytes, base_url: str) -> list[tuple[str, str]]:
    parser = _AnchorParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    out: dict[str, str] = {}
    for href, title in parser.anchors:
        url = urljoin(base_url, href)
        path = urlparse(url).path
        modern = re.search(
            r"/secondary-legislation/(agency|pco)-drafted/([^/]+)/([^/]+)/"
            r"en/latest(?:/|$)",
            path,
        )
        classic = re.search(
            r"/regulation/public/([^/]+)/([^/]+)/latest(?:/|$)",
            path,
        )
        if modern is not None:
            publisher, year, number = modern.groups()
            url = (
                "https://www.legislation.govt.nz/secondary-legislation/"
                f"{publisher}-drafted/{year}/{number}/en/latest/"
            )
        elif classic is not None:
            year, number = classic.groups()
            url = (
                "https://www.legislation.govt.nz/secondary-legislation/"
                f"pco-drafted/{year}/{int(number)}/en/latest/"
            )
        else:
            continue
        out[url] = title or out.get(url, "")
    return sorted(out.items())


def _instrument_xml_url(eli: str) -> str:
    """Return the official XML-format variation for a current-version ELI."""

    parsed = urlparse(eli)
    if parsed.scheme != "https" or parsed.netloc != "www.legislation.govt.nz":
        raise CaptureError(f"instrument is not an official NZ ELI: {eli}")
    return eli.rstrip("/") + ".xml"


def _live_instrument_row(
    session: requests.Session,
    *,
    eli: str,
    listing_title: str,
    act: Act,
    status_as_of: dt.date,
) -> dict[str, Any]:
    """Fetch one instrument's official XML and derive exact DK-v1 metadata.

    The Act page is only the candidate-set source.  As in the DK capture, each
    candidate's own authoritative representation supplies the date, title,
    document type, and force status.  Missing XML or metadata fails the whole
    live capture instead of being replaced by a year or assumed ``in_force``.
    """

    xml_url = _instrument_xml_url(eli)
    response = session.get(
        xml_url,
        headers={"Accept": "application/xml,text/xml;q=0.9"},
        timeout=90,
    )
    response.raise_for_status()
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise CaptureError(f"{xml_url}: official XML is malformed: {exc}") from exc
    path = Path(urlparse(eli).path)
    date_document = (
        root.get("date.signed")
        or root.get("date.gazetted")
        or root.get("date.first.valid")
        or root.get("date.as.at")
        or ""
    )
    first_valid = _xml_date(root.get("date.first.valid"))
    terminated = _xml_date(root.get("date.terminated"))
    in_force = (first_valid is None or first_valid <= status_as_of) and (
        terminated is None or status_as_of < terminated
    )
    title = _first_text(root, "title") or listing_title
    if not title:
        raise CaptureError(f"{xml_url}: official XML has no instrument title")
    try:
        year, number = _work_parts(path)
    except CaptureError:
        match = re.search(r"/regulation/public/([^/]+)/([^/]+)", path.as_posix())
        if match is None:
            raise
        year, number = match.groups()
    series = "SL" if int(year) >= 2022 else "LI" if int(year) >= 2012 else "SR"
    pursuant = _pursuant_text(root)
    return {
        "eli": eli,
        "relation": "basis_for",
        "date_document": date_document,
        "type_document": _instrument_type(root),
        "in_force": in_force,
        "title": title,
        "title_short": f"{series} {year}/{int(number)}",
        "act_eli": act.eli,
        "act_citation_path": act.citation_path,
        "empowering_provisions": pursuant
        or "Act relationship supplied by the authoritative Secondary legislation listing; XML exposes no pursuant text",
        "retrieval_method": "instrument's official latest-version XML format",
        "source_sha256": _sha256(response.content),
    }


def _live_capture(
    session: requests.Session,
    *,
    status_as_of: dt.date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for act in ACTS:
        response = session.get(act.listing_url, timeout=90)
        response.raise_for_status()
        links = _extract_instrument_links(response.content, response.url)
        if len(links) != act.reported_count:
            raise CaptureError(
                f"{act.title}: Act-page response exposed {len(links)} unique rows, "
                f"not advertised total {act.reported_count}; capture the tab's "
                "paginated related-legislation response on a browser-capable runner"
            )
        for index, (url, title) in enumerate(links):
            if index:
                time.sleep(0.1)
            rows.append(
                _live_instrument_row(
                    session,
                    eli=url,
                    listing_title=title,
                    act=act,
                    status_as_of=status_as_of,
                )
            )
        receipts.append(
            {
                "act_eli": act.eli,
                "act_citation_path": act.citation_path,
                "listing_url": response.url,
                "classic_cross_check_url": act.classic_listing_url,
                "response_sha256": _sha256(response.content),
                "reported_count": act.reported_count,
                "captured_count": len(links),
                "unresolved_count": 0,
                "method": (
                    "official Act-page response exposing the complete Secondary "
                    "legislation tab"
                ),
                "complete": True,
            }
        )
    return rows, receipts


def _supplemental_rows(
    *,
    session: requests.Session | None = None,
    retrieved_at: str | None = None,
) -> list[dict[str, Any]]:
    acts = {act.title: act for act in ACTS}
    rows = []
    for source in SUPPLEMENTAL_INSTRUMENTS:
        source = dict(source)
        act = acts[source.pop("act")]
        citation_path = source.get("corpus_citation_path")
        if isinstance(citation_path, str):
            if citation_path == "nz/guidance/acc/client-payment-rates-2025-04":
                provenance = {
                    "corpus_commit": _CORPUS_GUIDANCE_COMMIT,
                    "corpus_manifest": _APRIL_2025_MANIFEST,
                    "corpus_manifest_sha256": _APRIL_2025_MANIFEST_SHA256,
                    "retrieval_method": (
                        "axiom-corpus guidance-manifest entry at the recorded "
                        "commit; the manifest records browser-rendered content "
                        "verification but no harvested source-byte digest"
                    ),
                }
            else:
                source_sha256 = _CORPUS_SOURCE_SHA256.get(citation_path)
                if source_sha256 is None:
                    raise CaptureError(
                        f"missing corpus guidance receipt for {citation_path}"
                    )
                provenance = {
                    "corpus_commit": _CORPUS_GUIDANCE_COMMIT,
                    "corpus_manifest": _CORPUS_GUIDANCE_INVENTORY,
                    "corpus_manifest_sha256": _CORPUS_GUIDANCE_INVENTORY_SHA256,
                    "source_sha256": source_sha256,
                    "retrieval_method": (
                        "axiom-corpus guidance-inventory replay; manifest and "
                        "harvested official-page bytes identified by SHA-256"
                    ),
                }
        else:
            provenance = {
                "retrieval_method": (
                    "authoritative publisher URL metadata reviewed 2026-08-19; "
                    "raw response bytes were unavailable to this capture"
                )
            }
        eli = source.pop("eli")
        if session is not None:
            response = session.get(eli, timeout=90)
            response.raise_for_status()
            if not response.content:
                raise CaptureError(f"{eli}: supplemental publisher returned no bytes")
            provenance.update(
                {
                    "publisher_response_sha256": _sha256(response.content),
                    "publisher_response_retrieved_at": retrieved_at,
                    "retrieval_method": (
                        provenance["retrieval_method"]
                        + "; live authoritative publisher response fetched and SHA-256 bound"
                    ),
                }
            )
        rows.append(
            {
                "eli": eli,
                "relation": "bears_on",
                "date_document": source.pop("date_document"),
                "type_document": source.pop("type_document"),
                "in_force": True,
                "title": source.pop("title"),
                "title_short": source.pop("title_short"),
                "act_eli": act.eli,
                "act_citation_path": act.citation_path,
                **provenance,
                **source,
            }
        )
    return rows


def _unique_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_eli: dict[str, dict[str, Any]] = {}
    for row in rows:
        eli = row["eli"]
        if eli in by_eli:
            raise CaptureError(f"duplicate instrument ELI/URL: {eli}")
        by_eli[eli] = row
    return sorted(
        by_eli.values(),
        key=lambda row: (
            str(row["act_citation_path"]),
            str(row["relation"]),
            str(row["eli"]),
        ),
    )


def build_snapshot(
    *,
    retrieved_at: str,
    offline_pco_root: Path | None = None,
    offline_manifest: Path | None = None,
    offline_source_retrieved_at: str | None = None,
) -> dict[str, Any]:
    try:
        status_as_of = dt.date.fromisoformat(retrieved_at)
    except ValueError as exc:
        raise CaptureError("--retrieved-at must be an ISO date") from exc
    if offline_pco_root is None:
        session = requests.Session()
        session.headers.update(
            {
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "axiom-oracles-nz-instrument-capture/1",
            }
        )
        official, receipts = _live_capture(session, status_as_of=status_as_of)
        supplemental = _supplemental_rows(
            session=session,
            retrieved_at=retrieved_at,
        )
        method = (
            "legislation.govt.nz Act-page Secondary legislation responses; each "
            "raw response is SHA-256 receipted, complete tab rows and exact "
            "document metadata are mandatory, and row counts must equal the "
            "advertised totals; classic pages are PCO-only cross-checks; "
            "supplemental rows carry their own retrieval methods"
        )
    else:
        if offline_manifest is None:
            raise CaptureError(
                "offline replay requires the exact PCO download manifest"
            )
        if offline_source_retrieved_at is None:
            raise CaptureError(
                "offline replay requires the source retrieval date"
            )
        try:
            source_retrieved_at = dt.date.fromisoformat(
                offline_source_retrieved_at
            )
        except ValueError as exc:
            raise CaptureError(
                "--offline-source-retrieved-at must be an ISO date"
            ) from exc
        official, receipts = _offline_capture(
            offline_pco_root,
            offline_manifest,
            source_retrieved_at=source_retrieved_at,
            status_as_of=status_as_of,
        )
        method = (
            "INCOMPLETE OFFLINE REPLAY: 2026-06-16 official PCO API v0 XML "
            "download filtered by each instrument's pursuant text, checked "
            "against live 2026-08-19 Act-tab totals; agency-published and other "
            "unresolved listing rows are intentionally not invented; "
            "supplemental rows carry their own retrieval methods"
        )
        supplemental = _supplemental_rows()
    instruments = _unique_rows([*official, *supplemental])
    for row in instruments:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row["date_document"])):
            raise CaptureError(
                f"{row['eli']}: capture did not obtain an exact document date"
            )
    return {
        "schema": SCHEMA,
        "schema_compatibility_note": SCHEMA_COMPATIBILITY_NOTE,
        "act_eli": [act.eli for act in ACTS],
        "act_citation_path": [act.citation_path for act in ACTS],
        "retrieved_at": retrieved_at,
        "retrieval_method": method,
        "retrieval_receipts": receipts,
        "instruments": instruments,
    }


def serialize(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n"


def _diff(committed: dict[str, Any], fresh: dict[str, Any]) -> bool:
    old = {row["eli"]: row for row in committed.get("instruments", [])}
    new = {row["eli"]: row for row in fresh.get("instruments", [])}
    changed = False
    for label, values in (
        ("added", sorted(set(new) - set(old))),
        ("removed", sorted(set(old) - set(new))),
        (
            "changed",
            sorted(eli for eli in set(old) & set(new) if old[eli] != new[eli]),
        ),
    ):
        for eli in values:
            print(f"{label}: {eli}")
            changed = True
    if committed.get("retrieval_receipts") != fresh.get("retrieval_receipts"):
        print("changed: retrieval_receipts")
        changed = True
    if not changed:
        print("NZ instrument graph unchanged")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diff", action="store_true", help="print drift, write nothing")
    parser.add_argument("--output", type=Path, default=SNAPSHOT_PATH)
    parser.add_argument("--retrieved-at", default=dt.date.today().isoformat())
    parser.add_argument("--offline-pco-root", type=Path)
    parser.add_argument("--offline-manifest", type=Path)
    parser.add_argument("--offline-source-retrieved-at")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="required for offline replay; the resulting graph stays open",
    )
    args = parser.parse_args(argv)
    if args.offline_pco_root is not None and not args.allow_incomplete:
        parser.error("--offline-pco-root requires --allow-incomplete")
    if (
        args.offline_pco_root is not None
        and args.offline_source_retrieved_at is None
    ):
        parser.error(
            "--offline-pco-root requires --offline-source-retrieved-at"
        )
    if args.offline_pco_root is not None and args.offline_manifest is None:
        parser.error("--offline-pco-root requires --offline-manifest")
    try:
        snapshot = build_snapshot(
            retrieved_at=args.retrieved_at,
            offline_pco_root=args.offline_pco_root,
            offline_manifest=args.offline_manifest,
            offline_source_retrieved_at=args.offline_source_retrieved_at,
        )
        rendered = serialize(snapshot)
        if args.diff:
            if not args.output.exists():
                print(f"no committed snapshot at {args.output}", file=sys.stderr)
                return 1
            committed = json.loads(args.output.read_text())
            return int(_diff(committed, snapshot))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    except (CaptureError, OSError, requests.RequestException, json.JSONDecodeError) as exc:
        print(f"NZ instrument capture ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"wrote {args.output}: {len(snapshot['instruments'])} rows "
        f"as of {snapshot['retrieved_at']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
