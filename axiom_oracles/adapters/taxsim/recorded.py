"""Verified replay of the paired outputs in a pe-taxsim comparison release.

Both sides are observations from the release, with identical population inputs.
Loading validates the entire pair before exposing adapters, including records
that a caller might otherwise silently exclude by selecting a population subset.
No TAXSIM executable or PolicyEngine simulation runs here.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import tempfile
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...comparison.mappings import engine_targets_for_concepts
from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.results import EngineResult
from ...populations.taxsim_csv import TAXSIM_INPUT_COLUMNS
from ..policyengine.taxsim_runner import _taxsim_to_policyengine_pairs
from . import pins
from .projection import _TAXSIM_STATE_CODES

DEFAULT_REPO = "PolicyEngine/policyengine-taxsim"
DEFAULT_TAG = "full-ecps-comparison-run-35953332152"
SHA256_BY_YEAR = {
    2021: "04e23f1fe3c3cf46011fa75e0ee5fcbab86d10ec60fb44015776e1bba734d2c0",
    2022: "8440c6713ed8b8a51737a3a04ff6a0a5d2f81066c23de128b67c2155991bd58e",
    2023: "9c4635a1d365f6eb91d3eafe04be07f602297f1befa0139e2fbbc7cf405c1c92",
    2024: "6e1692d55957177fb336434d28ed21cb1b1763f28a8284409e3633b82ce437db",
    2025: "22d6d4b2b40e5b3d8e81636e98ace2791de5416b5d6c1f5abf24487a51125a14",
}
# Computed from the release's provenance assets, alongside the CSV pins above.
PROVENANCE_SHA256_BY_YEAR = {
    2021: "989a4259fad39270695411ed1a81c9e774a68b96408c846833f7fa5b545cff4e",
    2022: "878a1fe43a77c69436fe11828d3431d4069bbcc04dcb1d3e4dbbfd4d76d37eed",
    2023: "3e2aab1607253fcb2249424ddb0c606835f8cec7e40bf66da4aa47ff3d1f8c42",
    2024: "d43b4b54c3e812bec704fb1983f7da56872808422cced0a996beeccb412142e8",
    2025: "50dfff3c15b6d3036c8b6d6a0ff3b24a9984cd607be4ac1bdb22f2702f5254f3",
}
OUTPUT_COLUMNS = frozenset(
    {
        "fiitax", "siitax", "fica", "frate", "srate", "ficar", "tfica",
        "staxbc", "srebate", "senergy", "sctc", "sptcr", "samt", "qbid",
        "niit", "addmed", "cares", "actc", *(f"v{i}" for i in range(10, 44)),
    }
)
_SOURCES = ("taxsim", "policyengine")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_EMULATOR_FIELDS = (
    "emulatorCommit", "policyengineUsVersion", "policyengineCoreVersion",
    "spmCalculatorVersion", "assumeW2Wages", "disableSalt",
    "policyengineOutputDetail", "requirementsSha256", "scriptSha256",
)


class RecordedReleaseError(ValueError):
    """Recorded outputs cannot be tied to the requested population and pins."""


def release_sha256_by_year(repo: str = DEFAULT_REPO, tag: str = DEFAULT_TAG) -> dict[int, str]:
    """Return built-in CSV pins, or fail rather than trusting a download."""
    if (repo, tag) != (DEFAULT_REPO, DEFAULT_TAG):
        raise RecordedReleaseError(f"No built-in recorded-release pins for {repo}@{tag}")
    return dict(SHA256_BY_YEAR)


@dataclass
class RecordedRelease:
    """A complete, validated release year and adapters over its paired rows."""

    identity: dict[str, Any]
    pin_profile: str
    _records: dict[str, dict[str, dict[str, Any]]] = field(repr=False)
    _binary_usage: Counter = field(repr=False)

    def adapter(self, engine: str) -> RecordedReleaseAdapter:
        if engine not in _SOURCES:
            raise RecordedReleaseError(f"Recorded-release engine must be one of {_SOURCES}")
        return RecordedReleaseAdapter(self, engine)

    def taxsim_identity(self) -> dict[str, Any]:
        binaries = []
        for (sha, scope), count in self._binary_usage.items():
            binary = pins.pinned_binary(sha)
            binaries.append({
                "sha256": sha,
                "build": binary.build,
                "build_observed": None,
                "platform": "linux",
                "bytes": binary.bytes,
                "rows": count,
                "scope": scope,
            })
        binaries.sort(key=lambda item: (item["scope"] != pins.DEFAULT_SCOPE,
                                        item["scope"], item["sha256"]))
        return {"pin_profile": self.pin_profile, "binaries": binaries}

    def policyengine_identity(self) -> dict[str, Any]:
        provenance = self.identity["provenance"]
        return {"mode": "recorded-release", **{
            key: provenance[key] for key in _EMULATOR_FIELDS if key in provenance
        }}


class RecordedReleaseAdapter(EngineAdapter):
    """Replay one side in requested case order, allowing comparator batches."""

    def __init__(self, release: RecordedRelease, engine: str) -> None:
        self.release = release
        self.name = engine

    def taxsim_identity(self) -> dict[str, Any] | None:
        return self.release.taxsim_identity() if self.name == "taxsim" else None

    def run_cases(self, cases: list[Case], variables: list[str] | None = None) -> list[EngineResult]:
        records = self.release._records[self.name]
        missing = sum(case.case_id not in records for case in cases)
        if missing:
            raise RecordedReleaseError(f"Recorded {self.name} batch has missing={missing} cases")
        taxsim_targets = None
        policyengine_pairs = (
            _taxsim_to_policyengine_pairs(variables)
            if variables is not None and self.name == "policyengine" else None
        )
        if variables is not None and self.name == "taxsim":
            taxsim_targets = []
            for variable in variables:
                taxsim_targets.extend(engine_targets_for_concepts([variable], "taxsim") or [variable])
        results = []
        for case in cases:
            record = records[case.case_id]
            if self.name == "policyengine":
                values = (
                    {target: record[column] for column, target in policyengine_pairs.items()
                     if column in record}
                    if policyengine_pairs is not None else dict(record)
                )
            else:
                values = {key: value for key, value in record.items()
                          if key in (taxsim_targets if taxsim_targets is not None else OUTPUT_COLUMNS)}
            results.append(EngineResult(engine=self.name, household_id=case.case_id,
                                        values=values, raw=record))
        return results


def _checked_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise RecordedReleaseError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _verify_bytes(data: bytes, expected: str, label: str) -> str:
    _checked_sha(expected, f"{label} pin")
    observed = hashlib.sha256(data).hexdigest()
    if observed != expected:
        raise RecordedReleaseError(f"{label} sha256 mismatch: expected {expected}, observed {observed}")
    return observed


def _provenance(data: bytes, year: int) -> dict[str, Any]:
    try:
        provenance = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise RecordedReleaseError(f"provenance_{year}.json is not valid JSON: {exc}") from exc
    if not isinstance(provenance, dict) or provenance.get("year") != year:
        raise RecordedReleaseError(f"provenance year differs from requested year {year}")
    for key in ("outputSha256", "sourceSha256", "taxsimBinarySha256"):
        _checked_sha(provenance.get(key), f"provenance {key}")
    for key in ("emulatorCommit", "policyengineUsVersion", "policyengineCoreVersion"):
        if not isinstance(provenance.get(key), str) or not provenance[key]:
            raise RecordedReleaseError(f"provenance {key} must be a nonempty string")
    for key in ("assumeW2Wages", "disableSalt"):
        if not isinstance(provenance.get(key), bool):
            raise RecordedReleaseError(f"provenance {key} must be a boolean")
    if type(provenance.get("policyengineOutputDetail")) is not int:
        raise RecordedReleaseError("provenance policyengineOutputDetail must be an integer")
    return provenance


def _number(value: Any, label: str) -> int | float:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value):
        return int(value)
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise RecordedReleaseError(f"{label} is not numeric: {value!r}") from exc
    if not math.isfinite(number):
        raise RecordedReleaseError(f"{label} is not finite: {value!r}")
    return int(number) if number.is_integer() else number


def _id(value: Any, label: str) -> int:
    number = _number(value, label)
    if not isinstance(number, int):
        raise RecordedReleaseError(f"{label} is not an integer: {value!r}")
    return number


def _recorded_binary(row: Mapping[str, str], provenance: Mapping[str, Any], state: int, year: int) -> str:
    if row.get("taxsim_binary_sha256"):
        return _checked_sha(row["taxsim_binary_sha256"], "row taxsim_binary_sha256")
    fallback = provenance.get("taxsimFallback")
    if fallback:
        if not isinstance(fallback, Mapping):
            raise RecordedReleaseError("provenance taxsimFallback must be an object")
        states = {_TAXSIM_STATE_CODES.get(s, s) for s in fallback.get("states", [])}
        if state in states and year in fallback.get("years", []):
            return _checked_sha(fallback.get("sha256"), "taxsimFallback sha256")
    return provenance["taxsimBinarySha256"]


def load_recorded_release(
    directory: str | os.PathLike[str], *, cases: list[Case],
    dataset_identity: Mapping[str, Any], year: int | str,
    expected_sha256: str, repo: str = DEFAULT_REPO, tag: str = DEFAULT_TAG,
    pin_profile: str | None = None,
) -> RecordedRelease:
    """Validate a release year against its suite, population and Linux pins.

    Inputs are compared after the population loader's year override. Only
    numeric parsing noise (relative error <= 1e-9, zero absolute tolerance)
    is accepted. Each engine must contain exactly one row for every case.
    """
    year = _id(year, "requested year")
    directory = Path(directory).expanduser()
    filename = f"comparison_results_{year}.csv"
    provenance_filename = f"provenance_{year}.json"
    try:
        provenance_bytes = (directory / provenance_filename).read_bytes()
        data = (directory / filename).read_bytes()
    except OSError as exc:
        raise RecordedReleaseError(f"Cannot read recorded release {directory}: {exc}") from exc
    provenance = _provenance(provenance_bytes, year)
    observed = _verify_bytes(data, expected_sha256, f"{filename} suite pin")
    _verify_bytes(data, provenance["outputSha256"], f"{filename} provenance outputSha256")
    dataset_sha = _checked_sha(dataset_identity.get("sha256"), "population sha256")
    if provenance["sourceSha256"] != dataset_sha:
        raise RecordedReleaseError("provenance sourceSha256 differs from population sha256: "
                                   f"{provenance['sourceSha256']} != {dataset_sha}")
    cases_by_id = {}
    for case in cases:
        if case.metadata.get("population") != "taxsim-csv":
            raise RecordedReleaseError("Recorded releases require taxsim-csv cases")
        if case.metadata.get("dataset_sha256") != dataset_sha:
            raise RecordedReleaseError(f"case {case.case_id} dataset_sha256 differs from population")
        inputs = case.metadata.get("taxsim_input")
        if not isinstance(inputs, Mapping):
            raise RecordedReleaseError(f"case {case.case_id} has no taxsim_input")
        taxsimid = _id(inputs.get("taxsimid"), f"case {case.case_id} taxsimid")
        if taxsimid in cases_by_id:
            raise RecordedReleaseError(f"Duplicate case taxsimid {taxsimid}")
        cases_by_id[taxsimid] = case
    if len({case.case_id for case in cases}) != len(cases):
        raise RecordedReleaseError("Duplicate case ids")
    profile = pins.get_profile(pins.active_profile_name(pin_profile))
    records: dict[str, dict[str, dict[str, Any]]] = {source: {} for source in _SOURCES}
    seen: dict[str, set[int]] = {source: set() for source in _SOURCES}
    duplicates: Counter = Counter()
    binary_usage: Counter = Counter()
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
        header = reader.fieldnames or []
        if len(set(header)) != len(header):
            raise RecordedReleaseError("Recorded CSV has duplicate column names")
        if not {"source", "taxsimid", "state", "year", "fiitax", "siitax"} <= set(header):
            raise RecordedReleaseError("Recorded CSV requires source, taxsimid, state, year, fiitax, siitax")
        input_columns = set(header) & TAXSIM_INPUT_COLUMNS
        output_columns = set(header) & OUTPUT_COLUMNS
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise RecordedReleaseError(f"Recorded CSV row {line} has the wrong number of cells")
            source = row["source"]
            if source not in _SOURCES:
                raise RecordedReleaseError(f"Recorded CSV row {line} has unknown source {source!r}")
            taxsimid = _id(row["taxsimid"], f"row {line} taxsimid")
            if taxsimid in seen[source]:
                duplicates[source] += 1
                continue
            seen[source].add(taxsimid)
            case = cases_by_id.get(taxsimid)
            if case is None:
                continue
            inputs = case.metadata["taxsim_input"]
            for column in input_columns | set(inputs):
                value = row.get(column, "")
                expected = inputs.get(column)
                if value == "" and expected is None:
                    continue
                if value == "" or expected is None or not math.isclose(
                    _number(value, f"row {line} {column}"), expected, rel_tol=1e-9, abs_tol=0.0
                ):
                    raise RecordedReleaseError(f"Recorded input mismatch: source={source}, "
                                               f"taxsimid={taxsimid}, column={column}, "
                                               f"recorded={value!r}, case={expected!r}")
            record = {column: _number(row[column], f"row {line} {column}")
                      for column in output_columns if row[column] != ""}
            for required in ("fiitax", "siitax"):
                if required not in record:
                    raise RecordedReleaseError(f"Recorded {source} taxsimid={taxsimid} has no {required}")
            if source == "taxsim":
                state = _id(row["state"], f"row {line} state")
                recorded_year = _id(row["year"], f"row {line} year")
                if recorded_year != year:
                    raise RecordedReleaseError(f"Recorded row year {recorded_year} differs from {year}")
                resolution = profile.resolve(state, recorded_year, "linux")
                binary_sha = _recorded_binary(row, provenance, state, recorded_year)
                if binary_sha != resolution.sha256:
                    raise RecordedReleaseError(f"Recorded TAXSIM binary mismatch: taxsimid={taxsimid}, "
                                               f"state={state}, year={year}, profile={profile.name}, "
                                               f"expected={resolution.sha256}, observed={binary_sha}")
                binary_usage[(binary_sha, resolution.scope)] += 1
                record["taxsim_binary_sha256"] = binary_sha
            records[source][case.case_id] = record
    except (UnicodeDecodeError, csv.Error) as exc:
        raise RecordedReleaseError(f"Cannot parse recorded CSV: {exc}") from exc
    expected_ids = set(cases_by_id)
    counts = {source: {"missing": len(expected_ids - seen[source]),
                       "extra": len(seen[source] - expected_ids),
                       "duplicates": duplicates[source]} for source in _SOURCES}
    if any(count for side in counts.values() for count in side.values()):
        raise RecordedReleaseError("Recorded case set mismatch: " + "; ".join(
            f"{source} missing={side['missing']} extra={side['extra']} duplicates={side['duplicates']}"
            for source, side in counts.items()))
    if provenance.get("records") is not None and provenance["records"] != len(cases):
        raise RecordedReleaseError(f"provenance records={provenance['records']} differs from cases={len(cases)}")
    return RecordedRelease(
        identity={"repo": repo, "tag": tag, "file": filename, "sha256": observed,
                  "provenance_file": provenance_filename,
                  "provenance_sha256": hashlib.sha256(provenance_bytes).hexdigest(),
                  "provenance": provenance},
        pin_profile=profile.name, _records=records, _binary_usage=binary_usage,
    )


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=180) as response:
        return response.read()


def _write_verified(path: Path, data: bytes) -> None:
    """Atomically place bytes only after all integrity checks have passed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(data)
            handle.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def fetch_release(
    repo: str, tag: str, directory: str | os.PathLike[str], *,
    sha256_by_year: Mapping[int | str, str] | None = None,
    provenance_sha256_by_year: Mapping[int | str, str] | None = None,
    downloader: Callable[[str], bytes] | None = None,
) -> list[dict[str, Any]]:
    """Download pinned CSV/provenance pairs; never keep unverified bytes.

    Other releases require explicit pins for both assets. Existing verified
    assets are reused; an invalid existing file is never treated as a cache hit.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not tag:
        raise RecordedReleaseError("A GitHub owner/repo and nonempty release tag are required")
    known = (repo, tag) == (DEFAULT_REPO, DEFAULT_TAG)
    csv_pins = sha256_by_year if sha256_by_year is not None else release_sha256_by_year(repo, tag)
    provenance_pins = provenance_sha256_by_year
    if provenance_pins is None:
        if not known:
            raise RecordedReleaseError("Custom releases require provenance_sha256_by_year pins")
        provenance_pins = PROVENANCE_SHA256_BY_YEAR
    csv_pins = {int(year): _checked_sha(sha, f"CSV {year}") for year, sha in csv_pins.items()}
    provenance_pins = {int(year): _checked_sha(sha, f"provenance {year}")
                       for year, sha in provenance_pins.items()}
    if not csv_pins or not set(csv_pins) <= set(provenance_pins):
        raise RecordedReleaseError("Every release year requires CSV and provenance pins")
    download = downloader or _download
    directory = Path(directory).expanduser()
    base = f"https://github.com/{repo}/releases/download/{urllib.parse.quote(tag, safe='')}"
    assets = []
    for year, csv_sha in sorted(csv_pins.items()):
        names = (f"provenance_{year}.json", f"comparison_results_{year}.csv")
        data_by_name = {}
        for name, sha in zip(names, (provenance_pins[year], csv_sha), strict=True):
            path = directory / name
            data = path.read_bytes() if path.is_file() else None
            if data is None or hashlib.sha256(data).hexdigest() != sha:
                data = download(f"{base}/{name}")
            _verify_bytes(data, sha, name)
            data_by_name[name] = data
        provenance = _provenance(data_by_name[names[0]], year)
        _verify_bytes(data_by_name[names[1]], provenance["outputSha256"], f"{names[1]} provenance outputSha256")
        for name in names:
            data = data_by_name[name]
            _write_verified(directory / name, data)
            assets.append({"file": name, "path": str(directory / name),
                           "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    return assets
