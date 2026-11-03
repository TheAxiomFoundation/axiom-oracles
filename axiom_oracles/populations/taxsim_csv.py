"""TAXSIM-format CSV population loader (``--population taxsim-csv``).

The PolicyEngine TAXSIM emulator benchmark (PolicyEngine/policyengine-taxsim)
scores PolicyEngine against NBER TAXSIM over one TAXSIM-35 input file,
``cps_households.csv``: one row per tax unit, in TAXSIM's own column
vocabulary (``taxsimid``, ``year``, ``state`` as a TAXSIM/SOI code, ``mstat``,
``page``, ``pwages``, ...). This module loads such a file into :class:`Case`
objects so ``axiom-oracles`` can compare engines over exactly the rows the
benchmark ran, instead of re-projecting a population through
:func:`axiom_oracles.adapters.taxsim.projection.taxsim_input_for_case`.

Contract
--------
* **Verbatim rows.** Each row lands unchanged in ``case.metadata
  ["taxsim_input"]``, which :class:`~axiom_oracles.adapters.taxsim.runner.
  TaxsimPackageRunner` and :class:`~axiom_oracles.adapters.policyengine.
  taxsim_runner.PolicyEngineTaxsimRunner` pass through as-is. A cell whose
  text is an integer literal becomes an ``int``, any other numeric cell a
  ``float`` (Python's correctly rounded ``float()``), and a blank cell is
  omitted from the row. For every column with at least one non-blank cell
  (integers within int64), a DataFrame built from the rows has the dtype
  ``pandas.read_csv`` infers for the file and the values
  ``pandas.read_csv(float_precision="round_trip")`` parses;
  ``tests/test_taxsim_csv_population.py`` checks both. The
  benchmark's own worker reads its batch CSV with plain ``pd.read_csv``,
  whose default float parser is not correctly rounded: on the September
  benchmark file (sha256 ``ecabc8dd...``) it differs from the cell text in
  24,611 cells, by at most 2.0e-14 relative (measured with pandas 3.0.2).
  Non-numeric (including ``NA``-style tokens pandas would read as missing),
  non-finite, or non-ASCII cells fail the load.
* **State 0 stays 0.** TAXSIM state 0 is passed through, never remapped or
  rejected. pe-taxsim PR #1204 (commit ``2b69146b``) documents it as the code
  TAXSIM reads as "no state tax"; its commit message adds that the emulator's
  "Output echoes the input state (0 stays 0, as TAXSIM does)". A state-0 case
  therefore has no state geography: its scope is the whole US, so it appears
  only in national-scope comparisons. Any state code outside 0 and the
  TAXSIM/SOI codes in :mod:`axiom_oracles.adapters.taxsim.projection` fails
  the load, as does a blank state cell (a blank is not an explicit 0).
* **Year override.** ``period`` (a ``YYYY`` year) replaces every row's
  ``year`` — the benchmark runs one file for 2021-2025 this way
  (``scripts/refresh_dashboard.py`` builds ``dict(row, year=args.year)``).
  Without ``period`` each case keeps its row's year, which must be present.
* **Column vocabulary.** Header names must come from
  :data:`TAXSIM_INPUT_COLUMNS` unless ``allow_unknown_columns`` is set;
  ``taxsimid`` and ``state`` are required, ``taxsimid`` must be an integer and
  unique across the file, and duplicate header names fail the load.
* **Identity first.** The file is read once; its sha256 is computed over the
  same bytes that are parsed, and an ``expected_sha256`` mismatch raises
  :class:`TaxsimCsvIntegrityError` before any row is parsed or any case built.
  :func:`taxsim_csv_identity` describes the file (path, sha256, size, rows,
  columns, years, year override, per-state row counts, optional origin) for
  report provenance.
* **Unweighted.** Cases carry no ``household_weight`` (the :class:`Case` model
  does not require one), so report weighted totals equal case counts — the
  benchmark dashboard also counts tax units equally.

Case ids are ``taxsim-<taxsimid>``. Each case carries
``metadata["selector_facts"]`` (flat JSON scalars for disposition
predicates), a geography ``scope`` (``census_state`` from the SOI code, or
``country: US`` for state 0) and a ``locale`` (``US-<USPS>`` or ``US``).
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import os
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..adapters.taxsim.projection import _STATE_FIPS, _TAXSIM_STATE_CODES
from ..core.case import Case
from ..core.geography import GeographyScope, normalize_scope, scope_contains

#: ``Case.metadata["population"]`` and the identity ``source`` for this loader.
TAXSIM_CSV_SOURCE = "taxsim-csv"
#: Environment variable the CLI reads when ``--taxsim-csv`` is not passed.
TAXSIM_CSV_ENV_VAR = "AXIOM_TAXSIM_CSV"

#: TAXSIM-35 input columns this loader accepts. Copied, not invented, from the
#: two input-column lists in PolicyEngine/policyengine-taxsim at commit
#: a80b8c1dca088b147e36f9c770ed92d403d747f6: ``policyengine_taxsim/api.py``
#: ``KNOWN_COLUMNS`` ("All recognized TAXSIM input column names") plus
#: ``TaxsimRunner.OPTION_COLUMNS`` (``opt1``/``opt1v``) from
#: ``policyengine_taxsim/runners/taxsim_runner.py``. Their union contains every
#: name in ``TaxsimRunner.ALL_COLUMNS``; the test suite re-checks that against
#: the installed policyengine-taxsim when the ``taxsim`` extra is present.
#: ``age11`` is listed although that commit's TaxsimRunner drops dependent
#: ages above ``age10`` before invoking the binary; the benchmark file carries
#: an ``age11`` column.
TAXSIM_INPUT_COLUMNS: frozenset[str] = frozenset(
    {
        "taxsimid",
        "year",
        "state",
        "mstat",
        "page",
        "sage",
        "dependent_exemption",
        "depx",
        "pwages",
        "swages",
        "psemp",
        "ssemp",
        "dividends",
        "intrec",
        "stcg",
        "ltcg",
        "otherprop",
        "nonprop",
        "pensions",
        "gssi",
        "pui",
        "sui",
        "transfers",
        "rentpaid",
        "proptax",
        "otheritem",
        "childcare",
        "mortgage",
        "scorp",
        "pbusinc",
        "sbusinc",
        "pprofinc",
        "sprofinc",
        "idtl",
        *(f"age{index}" for index in range(1, 12)),
        "dep13",
        "dep17",
        "dep18",
        "opt1",
        "opt1v",
    }
)

#: Row columns copied into ``selector_facts`` (besides the derived state and
#: effective year). Values are the row's own numbers, integral floats rendered
#: as ints; a blank cell becomes ``None``.
SELECTOR_FACT_COLUMNS = ("mstat", "page", "sage", "depx", "idtl")

#: Default seed for :meth:`TaxsimCsvFile.select` sampling.
DEFAULT_SAMPLE_SEED = 0
#: Recorded in the selection summary so a report names how it sampled.
SAMPLE_METHOD = "sha256-rank"

_USPS_BY_TAXSIM_STATE: dict[int, str] = {
    code: usps for usps, code in _TAXSIM_STATE_CODES.items()
}
_SCOPE_BY_TAXSIM_STATE: dict[int, GeographyScope] = {
    0: GeographyScope(type="country", geoid="US"),
    **{
        code: GeographyScope(type="census_state", geoid=f"{_STATE_FIPS[usps]:02d}")
        for code, usps in _USPS_BY_TAXSIM_STATE.items()
    },
}
_REQUIRED_COLUMNS = ("taxsimid", "state")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,64}$")
_YEAR_PATTERN = re.compile(r"^\d{4}$")

Number = int | float


class TaxsimCsvError(ValueError):
    """A TAXSIM-format CSV that cannot be loaded as written."""


class TaxsimCsvIntegrityError(TaxsimCsvError):
    """The file's sha256 differs from the expected pin."""


@dataclass(frozen=True)
class TaxsimCsvSelection:
    """Cases selected from a file plus a JSON summary of how they were chosen."""

    cases: list[Case]
    summary: dict[str, Any]


@dataclass(frozen=True)
class TaxsimCsvFile:
    """A parsed, validated TAXSIM-format CSV.

    ``rows`` are the verbatim rows in file order, with the year override (if
    any) already applied; ``identity`` is the file-level provenance dict
    returned by :func:`taxsim_csv_identity`.
    """

    identity: dict[str, Any]
    rows: tuple[dict[str, Number], ...]

    def select(
        self,
        *,
        scope: GeographyScope | Mapping[str, Any] | None = None,
        sample_size: int | None = None,
        sample_seed: int = DEFAULT_SAMPLE_SEED,
    ) -> TaxsimCsvSelection:
        """Build cases for the rows inside ``scope``, optionally sampled.

        A row is inside ``scope`` when ``scope`` is ``None`` or contains the
        row's geography (``census_state`` for SOI codes 1-51, ``country: US``
        for state 0), so a single-state scope keeps only that state's rows and
        state-0 rows appear only under a national scope. ``sample_size`` of
        ``None`` or ``0`` keeps every in-scope row; a positive size keeps the
        rows whose ``sha256(f"{sample_seed}:{taxsimid}")`` digests sort
        lowest, returned in file order. That choice depends only on the seed
        and each row's ``taxsimid`` — not on file order or the Python
        version — so a sample is reproducible from the report alone.
        """
        normalized_scope = normalize_scope(scope)
        if sample_size is not None and sample_size < 0:
            raise ValueError("sample_size must be a non-negative integer.")
        in_scope: list[tuple[int, dict[str, Number]]] = []
        for index, row in enumerate(self.rows):
            if normalized_scope is None or scope_contains(
                normalized_scope, _row_scope(row)
            ):
                in_scope.append((index, row))
        chosen = in_scope
        if sample_size and sample_size < len(in_scope):
            ranked = sorted(
                in_scope,
                key=lambda item: _sample_rank(sample_seed, item[1]["taxsimid"]),
            )
            chosen = sorted(ranked[:sample_size], key=lambda item: item[0])
        sha256 = self.identity["sha256"]
        cases = [_case_for_row(row, index, sha256) for index, row in chosen]
        summary = {
            "scope": normalized_scope.as_dict() if normalized_scope else None,
            "rows_in_scope": len(in_scope),
            "sample_size": sample_size or None,
            "sample_seed": sample_seed if sample_size else None,
            "sample_method": SAMPLE_METHOD if sample_size else None,
            "cases": len(cases),
        }
        return TaxsimCsvSelection(cases=cases, summary=summary)


def read_taxsim_csv(
    path: str | os.PathLike[str],
    *,
    period: str | int | None = None,
    expected_sha256: str | None = None,
    origin: Mapping[str, Any] | None = None,
    allow_unknown_columns: bool = False,
) -> TaxsimCsvFile:
    """Read, hash, and validate a TAXSIM-format CSV (see the module contract)."""
    year_override = _year_override(period)
    # ``is not None``, not truthiness: an explicitly empty pin (e.g. an unset
    # shell variable) must fail validation, never silently disable it.
    expected = (
        _normalize_sha256(expected_sha256) if expected_sha256 is not None else None
    )
    normalized_origin = _normalize_origin(origin) if origin is not None else None

    file_path = Path(os.path.expandvars(os.path.expanduser(os.fspath(path))))
    data = file_path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    if expected is not None and sha256 != expected:
        raise TaxsimCsvIntegrityError(
            f"TAXSIM CSV {file_path} failed its sha256 check: expected "
            f"{expected}, got {sha256}. Refusing to load cases from a file "
            "other than the pinned one."
        )

    # Decode incrementally from the hashed bytes (no second full-text copy);
    # utf-8-sig drops a leading byte-order mark, as pandas.read_csv does.
    stream = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", newline="")
    # strict: malformed quoting raises instead of being silently repaired.
    reader = csv.reader(stream, strict=True)
    try:
        header = next(reader, None)
        if not header:
            raise TaxsimCsvError(f"TAXSIM CSV {file_path} has no header row.")
        unknown_columns = _validate_header(
            header,
            allow_unknown_columns=allow_unknown_columns,
            needs_year=year_override is None,
            source=file_path,
        )

        rows: list[dict[str, Number]] = []
        seen_ids: set[int] = set()
        duplicate_ids: set[int] = set()
        years_in_file: set[int] = set()
        state_counts: Counter[int] = Counter()
        for record in reader:
            if not record:
                continue  # blank line (pandas.read_csv skips these too)
            row_number = len(rows) + 1
            if len(record) != len(header):
                raise TaxsimCsvError(
                    f"TAXSIM CSV {file_path} data row {row_number} (line "
                    f"{reader.line_num}) has {len(record)} cells; the header "
                    f"has {len(header)}."
                )
            row = _parse_row(header, record, row_number=row_number, source=file_path)
            taxsimid = _required_integer(row, "taxsimid", row_number, file_path)
            state = _required_integer(row, "state", row_number, file_path)
            if state != 0 and state not in _USPS_BY_TAXSIM_STATE:
                raise TaxsimCsvError(
                    f"TAXSIM CSV {file_path} data row {row_number} has state "
                    f"{row['state']!r}, which is neither 0 (no state tax) nor a "
                    "TAXSIM/SOI state code (1-51)."
                )
            if taxsimid in seen_ids:
                duplicate_ids.add(taxsimid)
            seen_ids.add(taxsimid)
            if "year" in row:
                years_in_file.add(_required_integer(row, "year", row_number, file_path))
            elif year_override is None:
                raise TaxsimCsvError(
                    f"TAXSIM CSV {file_path} data row {row_number} has a blank "
                    "year and no period override was given."
                )
            state_counts[state] += 1
            if year_override is not None:
                # Same result as the benchmark's dict(row, year=...): an
                # existing year keeps its column position, else it is appended.
                row["year"] = year_override
            rows.append(row)
    except UnicodeDecodeError as exc:
        raise TaxsimCsvError(f"TAXSIM CSV {file_path} is not UTF-8: {exc}") from exc
    except csv.Error as exc:
        raise TaxsimCsvError(
            f"TAXSIM CSV {file_path} is malformed near line {reader.line_num}: {exc}"
        ) from exc

    if duplicate_ids:
        shown = ", ".join(str(item) for item in sorted(duplicate_ids)[:10])
        raise TaxsimCsvError(
            f"TAXSIM CSV {file_path} repeats taxsimid values ({shown}); every "
            "row must have a unique taxsimid."
        )

    identity: dict[str, Any] = {
        "source": TAXSIM_CSV_SOURCE,
        "path": _display_path(path),
        "filename": file_path.name,
        "sha256": sha256,
        "bytes": len(data),
        "rows": len(rows),
        "columns": list(header),
        "years_in_file": sorted(years_in_file),
        "year_override": year_override,
        # Explicit boolean so provenance (which drops null fields) still
        # records that no override was applied.
        "year_override_applied": year_override is not None,
        "state_counts": {
            str(code): state_counts[code] for code in sorted(state_counts)
        },
    }
    if unknown_columns:
        identity["unknown_columns"] = unknown_columns
    if normalized_origin is not None:
        identity["origin"] = normalized_origin
    return TaxsimCsvFile(identity=identity, rows=tuple(rows))


def taxsim_csv_identity(
    path: str | os.PathLike[str],
    *,
    period: str | int | None = None,
    expected_sha256: str | None = None,
    origin: Mapping[str, Any] | None = None,
    allow_unknown_columns: bool = False,
) -> dict[str, Any]:
    """Return the provenance identity of a TAXSIM-format CSV.

    Keys: ``source`` (``"taxsim-csv"``), ``path`` (as given, ``$HOME``-relative
    when under the home directory), ``filename``, ``sha256`` (64 hex of the file
    bytes), ``bytes``, ``rows``, ``columns`` (header order), ``years_in_file``,
    ``year_override`` (the applied ``period`` year or ``None``),
    ``state_counts`` (TAXSIM/SOI code as a string, including ``"0"``, to row
    count), plus ``origin`` (``{repo, commit, path}``) when supplied and
    ``unknown_columns`` when ``allow_unknown_columns`` admitted any.
    """
    return read_taxsim_csv(
        path,
        period=period,
        expected_sha256=expected_sha256,
        origin=origin,
        allow_unknown_columns=allow_unknown_columns,
    ).identity


def load_taxsim_csv_cases(
    path: str | os.PathLike[str],
    *,
    period: str | int | None = None,
    sample_size: int | None = None,
    expected_sha256: str | None = None,
    scope: GeographyScope | Mapping[str, Any] | None = None,
    origin: Mapping[str, Any] | None = None,
    allow_unknown_columns: bool = False,
    sample_seed: int = DEFAULT_SAMPLE_SEED,
) -> list[Case]:
    """Load a TAXSIM-format CSV as cases (see the module contract)."""
    return (
        read_taxsim_csv(
            path,
            period=period,
            expected_sha256=expected_sha256,
            origin=origin,
            allow_unknown_columns=allow_unknown_columns,
        )
        .select(scope=scope, sample_size=sample_size, sample_seed=sample_seed)
        .cases
    )


def parse_taxsim_csv_origin(value: str) -> dict[str, str]:
    """Parse ``REPO@COMMIT:PATH`` into ``{"repo", "commit", "path"}``.

    For example ``PolicyEngine/policyengine-taxsim@2b69146b...:cps_households.csv``.
    """
    repo, at, rest = value.partition("@")
    commit, colon, file_path = rest.partition(":")
    if not (at and colon):
        raise TaxsimCsvError(
            f"TAXSIM CSV origin {value!r} must look like REPO@COMMIT:PATH."
        )
    return _normalize_origin({"repo": repo, "commit": commit, "path": file_path})


def taxsim_state_usps(code: int) -> str | None:
    """USPS abbreviation for a TAXSIM/SOI state code; ``None`` for state 0."""
    if code == 0:
        return None
    try:
        return _USPS_BY_TAXSIM_STATE[code]
    except KeyError:
        raise TaxsimCsvError(f"Unknown TAXSIM/SOI state code {code!r}.") from None


def _validate_header(
    header: list[str],
    *,
    allow_unknown_columns: bool,
    needs_year: bool,
    source: Path,
) -> list[str]:
    duplicates = sorted(name for name, count in Counter(header).items() if count > 1)
    if duplicates:
        raise TaxsimCsvError(
            f"TAXSIM CSV {source} repeats header column(s): {', '.join(duplicates)}."
        )
    required = (*_REQUIRED_COLUMNS, "year") if needs_year else _REQUIRED_COLUMNS
    missing = [name for name in required if name not in header]
    if missing:
        raise TaxsimCsvError(
            f"TAXSIM CSV {source} lacks required column(s): {', '.join(missing)}."
        )
    unknown = [name for name in header if name not in TAXSIM_INPUT_COLUMNS]
    if unknown and not allow_unknown_columns:
        raise TaxsimCsvError(
            f"TAXSIM CSV {source} has column(s) outside the TAXSIM-35 input set: "
            f"{', '.join(repr(name) for name in unknown)}. Rename them, or pass "
            "allow_unknown_columns=True (--taxsim-csv-allow-unknown-columns) to "
            "pass them through verbatim."
        )
    return unknown


def _parse_row(
    header: list[str],
    record: list[str],
    *,
    row_number: int,
    source: Path,
) -> dict[str, Number]:
    row: dict[str, Number] = {}
    for column, cell in zip(header, record, strict=True):
        text = cell.strip()
        if not text:
            continue
        try:
            row[column] = _parse_number(text)
        except ValueError:
            raise TaxsimCsvError(
                f"TAXSIM CSV {source} data row {row_number} column {column!r} "
                f"holds {cell!r}, which is not a finite decimal number."
            ) from None
    return row


def _parse_number(text: str) -> Number:
    # int()/float() also accept non-ASCII digits and "_" separators, which
    # neither TAXSIM nor pandas.read_csv reads as numbers.
    if not text.isascii() or "_" in text:
        raise ValueError(text)
    try:
        return int(text)
    except ValueError:
        pass
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(text)
    return value


def _required_integer(
    row: Mapping[str, Number],
    column: str,
    row_number: int,
    source: Path,
) -> int:
    value = row.get(column)
    integer = _integer(value)
    if integer is None:
        raise TaxsimCsvError(
            f"TAXSIM CSV {source} data row {row_number} needs an integer "
            f"{column}; got {value!r}."
        )
    return integer


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _year_override(period: str | int | None) -> int | None:
    if period is None:
        return None
    text = str(period).strip()
    if not _YEAR_PATTERN.fullmatch(text):
        raise TaxsimCsvError(
            f"A TAXSIM CSV year override must be a YYYY year; got {period!r}."
        )
    return int(text)


def _normalize_sha256(value: str) -> str:
    text = str(value).strip().lower()
    if not _SHA256_PATTERN.fullmatch(text):
        raise TaxsimCsvError(
            f"expected_sha256 must be 64 hexadecimal characters; got {value!r}."
        )
    return text


def _normalize_origin(origin: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(origin, Mapping):
        raise TaxsimCsvError("TAXSIM CSV origin must be a mapping.")
    keys = set(origin)
    if keys != {"repo", "commit", "path"}:
        raise TaxsimCsvError(
            "TAXSIM CSV origin needs exactly repo, commit, and path; got "
            f"{sorted(keys)}."
        )
    normalized = {key: str(origin[key]).strip() for key in ("repo", "commit", "path")}
    if not all(normalized.values()):
        raise TaxsimCsvError("TAXSIM CSV origin repo, commit, and path must be set.")
    normalized["commit"] = normalized["commit"].lower()
    if not _COMMIT_PATTERN.fullmatch(normalized["commit"]):
        raise TaxsimCsvError(
            f"TAXSIM CSV origin commit {origin['commit']!r} is not a git hash."
        )
    return normalized


def _display_path(path: str | os.PathLike[str]) -> str:
    """The path as given, rewritten ``$HOME``-relative when under home."""
    given = os.fspath(path)
    expanded = os.path.expandvars(os.path.expanduser(given))
    if not os.path.isabs(expanded):
        return given
    try:
        relative = Path(expanded).relative_to(Path.home())
    except ValueError:
        return expanded
    return f"$HOME/{relative.as_posix()}"


def _row_scope(row: Mapping[str, Number]) -> GeographyScope:
    return _SCOPE_BY_TAXSIM_STATE[_integer(row["state"])]


def _sample_rank(seed: int, taxsimid: Number) -> bytes:
    return hashlib.sha256(f"{seed}:{_integer(taxsimid)}".encode()).digest()


def _case_for_row(row: dict[str, Number], index: int, sha256: str) -> Case:
    taxsimid = _integer(row["taxsimid"])
    state = _integer(row["state"])
    usps = taxsim_state_usps(state)
    year = _integer(row["year"])
    facts: dict[str, Any] = {
        "taxsim_state": state,
        "state": usps,
        "year": year,
    }
    for column in SELECTOR_FACT_COLUMNS:
        value = row.get(column)
        integer = _integer(value)
        if value is not None and integer is None:
            # Contract C3: these facts are integers; a fractional value would
            # silently defeat integer-valued disposition predicates.
            raise TaxsimCsvError(
                f"taxsimid {taxsimid}: {column}={value!r} is not an integer; "
                "selector facts require integer values."
            )
        facts[column] = integer
    return Case(
        case_id=f"taxsim-{taxsimid}",
        period=str(year),
        metadata={
            "population": TAXSIM_CSV_SOURCE,
            "dataset_sha256": sha256,
            "source_row": index + 1,
            "taxsim_input": row,
            "selector_facts": facts,
            "scope": _row_scope(row).as_dict(),
            "locale": f"US-{usps}" if usps else "US",
        },
    )


__all__ = [
    "DEFAULT_SAMPLE_SEED",
    "SAMPLE_METHOD",
    "SELECTOR_FACT_COLUMNS",
    "TAXSIM_CSV_ENV_VAR",
    "TAXSIM_CSV_SOURCE",
    "TAXSIM_INPUT_COLUMNS",
    "TaxsimCsvError",
    "TaxsimCsvFile",
    "TaxsimCsvIntegrityError",
    "TaxsimCsvSelection",
    "load_taxsim_csv_cases",
    "parse_taxsim_csv_origin",
    "read_taxsim_csv",
    "taxsim_csv_identity",
    "taxsim_state_usps",
]
