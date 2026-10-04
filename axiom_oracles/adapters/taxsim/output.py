"""Strict parser for the TAXSIM executable's stdout.

The NBER ``taxsimtest`` binary writes one CSV header plus one CSV row per input
record, but it also writes Fortran diagnostic text to the same stream. The
bundled macOS build (``cdate-20260521``) prints six copies of a line such as
``" d2       29126       25000         103         346"`` immediately *before*
the CSV rows of captured Utah profiles with $30,000 wages and primary filers
aged 73, 74, and 80. With ``idtl=0`` those lines even precede the header.
These fixtures establish behavior for the captured profiles, not an age-only
trigger. policyengine-taxsim parses the stream with ``pandas.read_csv`` and
coerces every column to numeric, which turns each diagnostic line into a
phantom row whose ``taxsimid`` is NaN. The resulting comparator failure in
fiit-taxsim-ecps batch 13 was reported on 2026-09-27; that historical batch
capture is not bundled here.

This module keeps the two kinds of line apart. A record line has the header's
field count and a numeric first field; every other non-blank line is a
diagnostic attributed to the record whose CSV row follows it, as observed in
the bundled fixtures. Historical solo/complement checks were also reported,
but their inputs and captures are not bundled. Diagnostics after the last
row are kept separately so the caller can decide whether they belong to a
record that produced no row.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from io import StringIO
from numbers import Integral, Real
from typing import Any

Scalar = float | int | str


@dataclass(frozen=True)
class TaxsimRecord:
    """One CSV row of TAXSIM output plus the diagnostics written before it."""

    id_key: str
    values: dict[str, Scalar]
    line_number: int
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaxsimStdout:
    """A parsed TAXSIM stdout stream."""

    header: tuple[str, ...]
    records: list[TaxsimRecord] = field(default_factory=list)
    #: Non-record lines after the last CSV row (or, with no rows at all, the
    #: whole stream). They belong to no parsed record.
    trailing_diagnostics: tuple[str, ...] = ()

    @property
    def diagnostic_count(self) -> int:
        return sum(len(record.diagnostics) for record in self.records) + len(
            self.trailing_diagnostics
        )


class TaxsimOutputError(RuntimeError):
    """The TAXSIM stdout stream could not be read as a record table."""


def parse_taxsim_stdout(text: str, *, id_column: str = "taxsimid") -> TaxsimStdout:
    """Split TAXSIM stdout into records and per-record diagnostics.

    The header is the first line whose first field is ``id_column``. Lines
    before it are diagnostics for the first record (the ``idtl=0`` layout). A
    line after the header is a record when it splits into as many fields as
    the header and its first field is numeric; anything else is a diagnostic
    for the next record. Blank lines carry nothing and are ignored.
    """
    lines = text.splitlines()
    header: tuple[str, ...] | None = None
    header_index = -1
    pending: list[str] = []
    for index, line in enumerate(lines):
        fields = _split(line)
        if fields and fields[0] == id_column:
            header = tuple(fields)
            header_index = index
            break
        if line.strip():
            pending.append(line)
    if header is None:
        raise TaxsimOutputError(
            f"TAXSIM stdout has no header line starting with {id_column!r}; "
            f"first lines: {lines[:5]!r}"
        )

    records: list[TaxsimRecord] = []
    for index in range(header_index + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        fields = _split(line)
        id_key = _numeric_id_key(fields[0]) if len(fields) == len(header) else None
        if id_key is None:
            pending.append(line)
            continue
        values = {column: _coerce(value) for column, value in zip(header, fields)}
        records.append(
            TaxsimRecord(
                id_key=id_key,
                values=values,
                line_number=index + 1,
                diagnostics=tuple(pending),
            )
        )
        pending = []
    return TaxsimStdout(
        header=header,
        records=records,
        trailing_diagnostics=tuple(pending),
    )


def id_key(value: Any) -> str:
    """Normalize an id so ``2116``, ``2116.0`` and ``"2116."`` agree."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, Real):
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return str(number)
    text = str(value).strip()
    numeric = _numeric_id_key(text)
    return numeric if numeric is not None else text


def _split(line: str) -> list[str]:
    try:
        [fields] = csv.reader(StringIO(line))
    except ValueError:
        return []
    return [item.strip() for item in fields]


def _numeric_id_key(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return id_key(number)


def _coerce(text: str) -> Scalar:
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer() and "." not in text and "e" not in text.lower():
        return int(number)
    return number
