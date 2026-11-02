"""Loader and hashing helpers for the pinned TAXSIM binary identity.

The axiom-oracles TAXSIM adapter shells out to a TAXSIM executable bundled
inside the ``policyengine-taxsim`` distribution (see ``runner.py``, which
imports ``TaxsimRunner`` dynamically). That binary is not vendored in this
repository, so reproducibility is pinned indirectly: ``taxsim_pins.json``
records the exact ``policyengine-taxsim`` release, its PyPI artifact hashes,
and the SHA-256 of each bundled executable.

This module reads that pin file and provides utilities to (a) resolve the
binary path an installed ``policyengine-taxsim`` would use, (b) recompute
its hash so a test can confirm the installed binary still matches the pin,
(c) refuse a law year the resolved binary does not model before running it
(:func:`require_law_years`), and (d) describe the binary a run used, for
report provenance (:func:`binary_identity`, :class:`TaxsimIdentityRecorder`).

In the pinned release the per-platform executables are different NBER builds
with different law-year ranges (each bundled binary's ``law_years`` in the
pin file), so the platform decides which law years can run.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .projection import _TAXSIM_STATE_CODES

PINS_PATH = Path(__file__).resolve().parent / "taxsim_pins.json"

# The NBER build stamp is a quoted literal in the executable's bytes, e.g.
# "cdate-20260521", "cdate-compdate" or "cd2026081819". The macOS and Linux
# builds print the same literal as the last column of their CSV header.
_BUILD_STAMP = r'"(cdate-[^"\s\x00]{1,32}|cd\d{10})"'
_BUILD_STAMP_BYTES = re.compile(_BUILD_STAMP.encode())
_BUILD_STAMP_TEXT = re.compile(_BUILD_STAMP)
_BUILD_STAMP_COLUMN = re.compile(r'^"?(cdate-[^"\s]{1,32}|cd\d{10})"?$')
# idtl=5 output has no CSV header; its banner names the build instead:
# " NBER TAXSIM @(#) $Version of: 20260521     With TCJA and BBB."
_VERBOSE_VERSION = re.compile(r"\$Version of:\s*(\S+)")

# Platform -> bundled-binary key in the pin file. Mirrors
# policyengine_taxsim.runners.taxsim_runner._get_taxsim_executable_path.
_PLATFORM_BINARY_KEY = {
    "linux": "taxsimtest/taxsimtest-linux.exe",
    "darwin": "taxsimtest/taxsimtest-osx.exe",
    "windows": "taxsimtest/taxsimtest-windows.exe",
}


@lru_cache(maxsize=1)
def load_pins() -> dict[str, Any]:
    """Return the parsed TAXSIM pin document."""
    return json.loads(PINS_PATH.read_text())


def pinned_version() -> str:
    """Return the pinned ``policyengine-taxsim`` version."""
    return str(load_pins()["distribution"]["version"])


def bundled_binaries() -> dict[str, dict[str, Any]]:
    """Return the mapping of bundled-binary relative path -> its pin entry.

    Each entry carries ``sha256``, ``bytes``, ``format``, ``build`` and
    ``law_years`` (``None`` for an executable that has not been run).
    """
    return dict(load_pins()["bundled_binaries"])


def platform_binary_key(system: str | None = None) -> str | None:
    """Return the pinned bundled-binary key for ``system`` (default: current)."""
    key = (system or platform.system()).lower()
    return _PLATFORM_BINARY_KEY.get(key)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def installed_binary_path(system: str | None = None) -> Path | None:
    """Return the path to the installed TAXSIM binary for ``system``, if present.

    Searches the ``policyengine-taxsim`` data-file install locations the runner
    itself uses. Returns ``None`` when ``policyengine-taxsim`` is not installed
    (so callers can skip rather than fail).
    """
    system = (system or platform.system()).lower()
    exe_name = {
        "linux": "taxsimtest-linux.exe",
        "darwin": "taxsimtest-osx.exe",
        "windows": "taxsimtest-windows.exe",
    }.get(system)
    if exe_name is None:
        return None

    subdir = Path("share") / "policyengine_taxsim" / "taxsimtest" / exe_name
    candidates = [
        Path(sys.prefix) / subdir,
        Path(sys.base_prefix) / subdir,
    ]
    real_prefix = getattr(sys, "real_prefix", None)
    if real_prefix:
        candidates.append(Path(real_prefix) / subdir)
    # uv's ephemeral `--with` overlay environments compose site-packages from
    # several cached archives, and sys.prefix points at a temp build dir that
    # carries no share/ tree at all — the wheel's data files land in the
    # archive that holds its site-packages. Walk every site-packages entry on
    # sys.path back to its env root (lib/pythonX.Y/site-packages → root) and
    # look for the shared-data tree there (#296).
    for entry in sys.path:
        path = Path(entry)
        if path.name == "site-packages" and len(path.parents) >= 3:
            candidates.append(path.parents[2] / subdir)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def resolve_binary_path(system: str | None = None) -> Path | None:
    """Resolve the executable used by preflight and the default runner.

    Preserve the adapter's installed share-tree preference (including uv
    overlays), then the upstream runner's native source-layout lookup.
    Return an absolute path so both callers select the same file.
    """
    installed = installed_binary_path(system)
    if installed is not None:
        return installed.resolve()
    key = platform_binary_key(system)
    if key is not None:
        source = Path("resources") / key
        if source.is_file():
            return source.resolve()
    return None


class TaxsimLawYearError(RuntimeError):
    """A requested law year lies outside the resolved TAXSIM binary's range."""


class TaxsimIdentityError(RuntimeError):
    """The binary that ran is not the binary that was hashed."""


def build_stamp_from_bytes(data: bytes) -> str | None:
    """Return the NBER build stamp embedded in an executable's bytes.

    ``None`` when the bytes carry no stamp, or more than one distinct stamp.
    """
    stamps = {match.decode() for match in _BUILD_STAMP_BYTES.findall(data)}
    return stamps.pop() if len(stamps) == 1 else None


def read_build_stamp(path: Path) -> str | None:
    """Read the embedded build stamp from an executable's bytes."""
    return build_stamp_from_bytes(Path(path).read_bytes())


def build_stamp_from_stdout(text: str) -> str | None:
    """Return the build stamp a TAXSIM run printed.

    CSV output (``idtl`` 0 and 2) ends its header with the quoted stamp;
    verbose ``idtl=5`` output names it in the ``$Version of:`` banner.
    """
    match = _BUILD_STAMP_TEXT.search(text) or _VERBOSE_VERSION.search(text)
    return match.group(1) if match else None


def build_stamp_from_columns(columns: Iterable[Any]) -> str | None:
    """Return the build stamp column of a parsed TAXSIM output table.

    ``pandas.read_csv`` (policyengine-taxsim's parser) keeps the header's
    stamp as a column name such as ``cdate-20260521``.
    """
    stamps = {
        match.group(1)
        for column in columns
        if (match := _BUILD_STAMP_COLUMN.match(str(column).strip()))
    }
    return stamps.pop() if len(stamps) == 1 else None


def same_build(left: str | None, right: str | None) -> bool:
    """Whether two build stamps name the same build.

    The CSV header prints ``cdate-20260521`` where the verbose banner prints
    ``20260521`` (and ``cd2026081819`` where it prints ``2026081819``).
    """
    if left is None or right is None:
        return False
    return normalize_build_stamp(left) == normalize_build_stamp(right)


def normalize_build_stamp(stamp: str) -> str:
    """Normalize equivalent CSV and verbose spellings of a build stamp."""
    stamp = stamp.strip().strip('"')
    if stamp.startswith("cdate-"):
        return stamp[len("cdate-") :]
    if re.fullmatch(r"cd\d{10}", stamp):
        return stamp[2:]
    return stamp


def pinned_entry_for_sha(sha256: str) -> tuple[str, dict[str, Any]] | None:
    """Return ``(key, entry)`` of the binary pinned with ``sha256``.

    A binary the pinned wheel bundles is found under its ``bundled_binaries``
    key (with its observed ``law_years``). Any other profile binary is found
    in the v2 ``binaries`` table under the key ``binaries/<sha256>``; its
    ``law_years`` is ``None`` unless the pin records one, so its range is
    unknown and :func:`require_law_years` does not refuse on it.
    """
    for key, entry in bundled_binaries().items():
        if entry["sha256"] == sha256:
            return key, dict(entry)
    meta = (load_pins().get("binaries") or {}).get(sha256)
    if isinstance(meta, Mapping):
        return f"binaries/{sha256}", {
            "sha256": sha256,
            "bytes": meta.get("bytes"),
            "build": meta.get("build"),
            "law_years": meta.get("law_years"),
        }
    return None


def law_year_range(entry: dict[str, Any] | None) -> tuple[int, int] | None:
    """Return the ``(first, last)`` law years a pinned binary accepts.

    The range is the one the binary states in the line it prints for a
    refused year; the pin's ``ran`` and ``rejected`` lists say which years
    were actually run. ``None`` when the binary has not been executed (its
    range is unknown).
    """
    years = (entry or {}).get("law_years")
    if not years:
        return None
    return int(years["first"]), int(years["last"])


def _host_platform(system: str | None = None) -> str:
    return (system or platform.system()).lower()


def _installed_package_version() -> str | None:
    try:
        return version("policyengine-taxsim")
    except PackageNotFoundError:
        return None


def binary_identity(path: Path, *, system: str | None = None) -> dict[str, Any]:
    """Describe an executable for provenance: path, hash, build and platform.

    The build stamp is read from the file's bytes. ``pinned_key`` and
    ``law_years`` come from the pin entry whose SHA-256 matches; both are
    ``None`` (and ``pinned`` is False) for a binary the pin does not record.
    """
    path = Path(path)
    data = path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    pinned = pinned_entry_for_sha(sha256)
    key, entry = pinned if pinned else (None, None)
    return {
        "path": str(path),
        "sha256": sha256,
        "bytes": len(data),
        "build": build_stamp_from_bytes(data),
        "platform": _host_platform(system),
        "machine": platform.machine() or None,
        "pinned": pinned is not None,
        "pinned_key": key,
        "law_years": _law_years_block(entry),
        "policyengine_taxsim": _installed_package_version(),
    }


def _law_years_block(entry: dict[str, Any] | None) -> dict[str, int] | None:
    years = law_year_range(entry)
    return None if years is None else {"first": years[0], "last": years[1]}


def require_law_years(
    years: Iterable[int],
    *,
    binary_path: Path | None = None,
    system: str | None = None,
    use_installed: bool = True,
) -> dict[str, Any] | None:
    """Refuse law years the TAXSIM binary that would run does not accept.

    The binary is ``binary_path`` when it exists, else (with ``use_installed``
    and no ``binary_path``) the installed or source-layout one resolved for
    ``system`` (default: this host), else the pinned binary for ``system``
    (what the ``taxsim`` extra installs). An existing binary is hashed
    before selecting its range: an unpinned hash, or a hash whose range is
    unknown, is not checked against any platform pin. Returns the identity
    of the existing binary that was resolved, else ``None``.

    Raises :class:`TaxsimLawYearError` naming the binary, its pinned range,
    the line it printed for a rejected year, and the pinned binaries that do
    accept the year.
    """
    requested = sorted({int(year) for year in years})
    if not requested:
        return None
    system = _host_platform(system)
    path = binary_path
    if path is not None and not Path(path).is_file():
        # A path that is not there cannot be hashed; the run will fail on it.
        # Check what this platform would install instead.
        path = None
    elif path is None and use_installed:
        path = resolve_binary_path(system)
    identity: dict[str, Any] | None = None
    if path is not None:
        identity = binary_identity(Path(path), system=system)
        pinned = pinned_entry_for_sha(identity["sha256"])
        if pinned is None:
            return identity
        key, entry = pinned
        where = f"{key} at {path}"
    else:
        key = platform_binary_key(system)
        if key is None:
            return None
        entry = bundled_binaries()[key]
        where = f"{key} as pinned"
    supported = law_year_range(entry)
    if supported is None:
        return identity
    first, last = supported
    rejected = [year for year in requested if not first <= year <= last]
    if not rejected:
        return identity
    raise TaxsimLawYearError(
        _law_year_message(rejected, system, where, entry, supported)
    )


def _law_year_message(
    rejected: list[int],
    system: str,
    where: str,
    entry: dict[str, Any],
    supported: tuple[int, int],
) -> str:
    first, last = supported
    shown = ", ".join(str(year) for year in rejected)
    noun = "law year" if len(rejected) == 1 else "law years"
    message = (
        f"TAXSIM cannot run {noun} {shown} on {system}: {where} (sha256 "
        f"{entry['sha256'][:12]}, build {entry.get('build')}, pinned for "
        f"policyengine-taxsim {pinned_version()}) accepts law years "
        f"{first}-{last} only."
    )
    observed = entry.get("law_years") or {}
    if observed.get("rejection") and observed.get("rejected"):
        tried = ", ".join(str(year) for year in observed["rejected"])
        message += (
            f" Run on {tried}, it printed {observed['rejection']!r} and exited 1."
        )
    by_platform = load_pins()["runtime_binary"]["by_platform"]
    alternatives = []
    not_run = []
    for other_system, other_key in by_platform.items():
        if other_system == system:
            continue
        other_range = law_year_range(bundled_binaries()[other_key])
        if other_range is None:
            not_run.append(other_system)
        elif all(other_range[0] <= year <= other_range[1] for year in rejected):
            alternatives.append(
                f"{other_system} ({other_key}, build "
                f"{bundled_binaries()[other_key].get('build')}, "
                f"{other_range[0]}-{other_range[1]})"
            )
    if alternatives:
        message += (
            f" The pinned binary for {' and '.join(alternatives)} accepts "
            f"{shown}: run there, or use a law year in {first}-{last}."
        )
    else:
        message += (
            f" No pinned binary that has been run accepts {shown}; use a law "
            f"year in {first}-{last}."
        )
    if not_run:
        message += f" (Not run, so unknown: the {', '.join(not_run)} binary.)"
    return f"{message} (Pinned ranges: axiom_oracles/adapters/taxsim/taxsim_pins.json.)"


def require_profile_law_years(
    years: Iterable[int],
    *,
    profile: str | None = None,
    system: str | None = None,
) -> None:
    """Refuse law years a profile's pinned binaries do not accept on ``system``.

    The profile default binary must accept every requested year; an override
    binary must accept the requested years its override covers. A binary
    whose range the pin does not record is not checked (its range is
    unknown), as in :func:`require_law_years`. The per-batch check in the
    runner still runs against the bytes it executes.
    """
    requested = sorted({int(year) for year in years})
    if not requested:
        return
    system = normalize_platform(system)
    chosen = get_profile(active_profile_name(profile))
    checks: list[tuple[str, list[int], str]] = []
    if system in chosen.binaries:
        checks.append((chosen.binaries[system], requested, DEFAULT_SCOPE))
    for override in chosen.overrides:
        covered = [year for year in requested if year in override.years]
        if covered and system in override.binaries:
            checks.append((override.binaries[system], covered, override.scope))
    for sha, wanted, scope in checks:
        pinned = pinned_entry_for_sha(sha)
        if pinned is None:
            continue
        key, entry = pinned
        supported = law_year_range(entry)
        if supported is None:
            continue
        first, last = supported
        rejected = [year for year in wanted if not first <= year <= last]
        if rejected:
            where = f"{key} ({scope} of pin profile {chosen.name!r})"
            raise TaxsimLawYearError(
                _law_year_message(rejected, system, where, entry, supported)
            )


class TaxsimIdentityRecorder:
    """Accumulate the identity of every TAXSIM binary a run executes.

    ``observe`` caches each binary's identity per path and keeps the build
    stamp its output printed. When given ``sha256`` (the pre-run hash), it
    hashes the file again after every invocation and requires that hash to
    equal both the pre-run and recorded hashes. A mismatch, or a printed
    stamp naming a different build, raises :class:`TaxsimIdentityError`
    before any identity or input rows from that batch are published.

    A file swapped and swapped back entirely within one invocation is not
    detected. These before/after checks do not provide full execution
    attestation.
    """

    def __init__(self) -> None:
        self._identities: dict[str, dict[str, Any]] = {}
        self._rows: dict[str, int] = {}
        self._observed: dict[str, str | None] = {}
        self._scopes: dict[str, dict[str, int]] = {}
        #: The pin profile that selected the binaries, when one did.
        self.pin_profile: str | None = None

    def observe(
        self,
        path: Path,
        *,
        rows: int,
        build_observed: str | None = None,
        sha256: str | None = None,
        scopes: Mapping[str, int] | None = None,
    ) -> dict[str, Any]:
        key = str(path)
        identity = self._identities.get(key)
        if identity is None:
            identity = binary_identity(Path(path))
        if sha256 is not None:
            post_sha256 = sha256_file(Path(path))
            if post_sha256 != sha256 or post_sha256 != identity["sha256"]:
                raise TaxsimIdentityError(
                    f"TAXSIM binary {path} changed during the run: sha256 "
                    f"{sha256[:12]} before a batch, {post_sha256[:12]} after, "
                    f"{identity['sha256'][:12]} recorded"
                )
        if build_observed is not None:
            if identity["build"] is not None and not same_build(
                identity["build"], build_observed
            ):
                raise TaxsimIdentityError(
                    f"TAXSIM printed build {build_observed!r}, but the file "
                    f"hashed at {path} (sha256 {identity['sha256'][:12]}) "
                    f"embeds build {identity['build']!r}"
                )
            previous = self._observed.get(key)
            if previous is not None and not same_build(previous, build_observed):
                raise TaxsimIdentityError(
                    f"TAXSIM binary {path} printed build {previous!r} and "
                    f"later {build_observed!r} in one run"
                )
        # Publish an identity only after its hash and printed build agree.
        if key not in self._identities:
            self._identities[key] = identity
            self._rows[key] = 0
            self._observed[key] = None
        if build_observed is not None:
            self._observed[key] = build_observed
        self._rows[key] += int(rows)
        for scope, count in (scopes or {}).items():
            bucket = self._scopes.setdefault(key, {})
            bucket[scope] = bucket.get(scope, 0) + int(count)
        return identity

    def binaries(self) -> list[dict[str, Any]]:
        entries = []
        for key, identity in self._identities.items():
            entry = {
                **identity,
                "build_observed": self._observed[key],
                "rows": self._rows[key],
            }
            if key in self._scopes:
                # Rows per profile scope ("default" or "override:<id>").
                entry["scopes"] = dict(sorted(self._scopes[key].items()))
            entries.append(entry)
        return entries

    def to_dict(self) -> dict[str, Any] | None:
        """The ``engine_identity.taxsim`` block, or ``None`` before any run."""
        if not self._identities:
            return None
        block: dict[str, Any] = {
            "pinned_policyengine_taxsim": pinned_version(),
            "binaries": self.binaries(),
        }
        if self.pin_profile is not None:
            block["pin_profile"] = self.pin_profile
        return block


# --------------------------------------------------------------------------
# Schema v2: pinned binaries, profiles and fail-closed resolution
#
# ``binaries`` pins every TAXSIM executable the adapter may run, keyed by
# SHA-256. ``profiles`` map each (TAXSIM SOI state, law year, platform) to one
# of them. The default runner resolves every row's binary from the active
# profile and executes only bytes whose SHA-256 and size equal the pin
# (:func:`locate_binary`); there is no fallback to another executable.

SCHEMA_VERSION = "axiom-oracles/taxsim-pin/v2"

PROFILE_ENV = "AXIOM_TAXSIM_PIN_PROFILE"
BINARY_DIR_ENV = "AXIOM_TAXSIM_BINARY_DIR"
CACHE_DIR_ENV = "AXIOM_TAXSIM_CACHE_DIR"
DEFAULT_CACHE_DIR = Path("~/.cache/axiom-oracles/taxsim-binaries")
SUITE_PROFILE_PARAMETER = "taxsim_pin_profile"
FETCH_COMMAND = "axiom-oracles taxsim fetch-binaries"

PLATFORMS = ("linux", "darwin", "windows")
DEFAULT_SCOPE = "default"
OVERRIDE_SCOPE_PREFIX = "override:"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SOURCE_KINDS = ("git", "url", "wheel")
_EVIDENCE_KINDS = ("documented", "computed")
_USPS_BY_TAXSIM_STATE = {code: usps for usps, code in _TAXSIM_STATE_CODES.items()}


class TaxsimPinError(RuntimeError):
    """A TAXSIM pin could not be resolved or verified (fail closed)."""


@dataclass(frozen=True)
class PinnedBinary:
    """One pinned TAXSIM executable."""

    sha256: str
    platform: str
    build: str
    bytes: int
    filename: str
    sources: tuple[Mapping[str, Any], ...]
    probe_results: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class Override:
    """A declarative (states x years) exception inside a profile."""

    id: str
    states: frozenset[int]
    years: frozenset[int]
    binaries: Mapping[str, str]

    @property
    def scope(self) -> str:
        return f"{OVERRIDE_SCOPE_PREFIX}{self.id}"

    def matches(self, state: int, year: int) -> bool:
        return state in self.states and year in self.years


@dataclass(frozen=True)
class Resolution:
    """The pinned binary one (state, year, platform) cell resolves to."""

    sha256: str
    scope: str


@dataclass(frozen=True)
class Profile:
    """A named mapping from (state, year, platform) to a pinned binary."""

    name: str
    description: str
    binaries: Mapping[str, str]
    overrides: tuple[Override, ...]

    @property
    def platforms(self) -> tuple[str, ...]:
        return tuple(p for p in PLATFORMS if p in self.binaries)

    def resolve(self, state: Any, year: Any, system: str | None = None) -> Resolution:
        """Resolve a row's (TAXSIM SOI state, year) on ``system``.

        State 0 is TAXSIM's "no state" code: no override names it, so it
        resolves to the profile default like any unlisted state.
        """
        system = normalize_platform(system)
        state_code = _integral(state, "state")
        if year is None:
            # A row with no law year cannot be matched against an override's
            # years. Resolve it only when no override could apply.
            if any(system in override.binaries for override in self.overrides):
                raise TaxsimPinError(
                    f"TAXSIM row has no year, and pin profile {self.name!r} "
                    "selects binaries by year; no pinned binary can be resolved"
                )
            sha = self.binaries.get(system)
            if sha is None:
                raise TaxsimPinError(
                    f"TAXSIM pin profile {self.name!r} names no {system} binary"
                )
            return Resolution(sha256=sha, scope=DEFAULT_SCOPE)
        year_value = _integral(year, "year")
        for override in self.overrides:
            if override.matches(state_code, year_value):
                sha = override.binaries.get(system)
                if sha is None:
                    raise TaxsimPinError(
                        f"TAXSIM pin profile {self.name!r} override "
                        f"{override.id!r} names no {system} binary"
                    )
                return Resolution(sha256=sha, scope=override.scope)
        sha = self.binaries.get(system)
        if sha is None:
            raise TaxsimPinError(
                f"TAXSIM pin profile {self.name!r} names no {system} binary"
            )
        return Resolution(sha256=sha, scope=DEFAULT_SCOPE)

    def binary_shas(self, system: str | None = None) -> list[str]:
        """Every binary this profile can resolve to (optionally one platform)."""
        systems = [normalize_platform(system)] if system else list(self.platforms)
        shas: list[str] = []
        for name in systems:
            for sha in [
                self.binaries.get(name),
                *(override.binaries.get(name) for override in self.overrides),
            ]:
                if sha and sha not in shas:
                    shas.append(sha)
        return shas


@dataclass(frozen=True)
class PinDocument:
    """The parsed, validated pin document."""

    default_profile: str
    binaries: Mapping[str, PinnedBinary]
    profiles: Mapping[str, Profile]
    probes: Mapping[str, Mapping[str, Any]]
    raw: Mapping[str, Any]



def validate_pin_document(doc: Mapping[str, Any]) -> list[str]:
    """Return every structural or consistency error in a v2 pin document."""
    errors: list[str] = []
    if doc.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION!r}, got "
            f"{doc.get('schema_version')!r}"
        )
    errors.extend(_validate_distribution(doc.get("distribution")))
    errors.extend(_validate_bundled(doc.get("bundled_binaries")))
    probes = doc.get("probes") or {}
    if not isinstance(probes, Mapping):
        errors.append("probes must be a mapping")
        probes = {}
    for probe_id, probe in probes.items():
        columns = probe.get("columns") if isinstance(probe, Mapping) else None
        values = probe.get("values") if isinstance(probe, Mapping) else None
        if (
            not isinstance(columns, list)
            or not isinstance(values, list)
            or len(columns) != len(values)
            or not columns
        ):
            errors.append(f"probes.{probe_id}: columns/values must be equal-length")

    binaries = doc.get("binaries")
    if not isinstance(binaries, Mapping) or not binaries:
        errors.append("binaries must be a non-empty mapping keyed by sha256")
        binaries = {}
    for sha, meta in binaries.items():
        errors.extend(_validate_binary(sha, meta, probes))

    profiles = doc.get("profiles")
    if not isinstance(profiles, Mapping) or not profiles:
        errors.append("profiles must be a non-empty mapping")
        profiles = {}
    for name, profile in profiles.items():
        errors.extend(_validate_profile(name, profile, binaries))

    default = doc.get("default_profile")
    if default not in profiles:
        errors.append(f"default_profile {default!r} is not a declared profile")
    bundled = doc.get("bundled_binaries")
    for key, entry in (bundled.items() if isinstance(bundled, Mapping) else ()):
        if not isinstance(entry, Mapping):
            continue
        meta = binaries.get(entry.get("sha256"))
        if not isinstance(meta, Mapping):
            continue
        if meta.get("bytes") != entry.get("bytes"):
            errors.append(
                f"binaries.{entry['sha256']}.bytes disagrees with "
                f"bundled_binaries.{key}.bytes"
            )
        if not same_build(meta.get("build"), entry.get("build")):
            errors.append(
                f"binaries.{entry['sha256']}.build disagrees with "
                f"bundled_binaries.{key}.build"
            )
    return errors


def _validate_distribution(dist: Any) -> list[str]:
    if not isinstance(dist, Mapping):
        return ["distribution must be a mapping"]
    errors = []
    if dist.get("package") != "policyengine-taxsim":
        errors.append("distribution.package must be 'policyengine-taxsim'")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(dist.get("version", ""))):
        errors.append("distribution.version must be X.Y.Z")
    for artifact in ("sdist", "wheel"):
        block = dist.get(artifact)
        if not isinstance(block, Mapping):
            errors.append(f"distribution.{artifact} must be a mapping")
            continue
        if not _SHA256_RE.match(str(block.get("sha256", ""))):
            errors.append(f"distribution.{artifact}.sha256 must be 64 hex")
        if not _positive_int(block.get("bytes")):
            errors.append(f"distribution.{artifact}.bytes must be a positive int")
        if not str(block.get("url", "")).startswith("https://files.pythonhosted.org/"):
            errors.append(f"distribution.{artifact}.url must be a PyPI file URL")
    return errors


def _validate_bundled(bundled: Any) -> list[str]:
    if not isinstance(bundled, Mapping) or not bundled:
        return ["bundled_binaries must be a non-empty mapping"]
    errors = []
    for key, meta in bundled.items():
        if not str(key).endswith(".exe"):
            errors.append(f"bundled_binaries key {key!r}")
        if not isinstance(meta, Mapping) or not _SHA256_RE.match(
            str(meta.get("sha256", ""))
        ):
            errors.append(f"bundled_binaries.{key}.sha256")
        elif not _positive_int(meta.get("bytes")):
            errors.append(f"bundled_binaries.{key}.bytes")
    return errors


def _validate_binary(sha: str, meta: Any, probes: Mapping[str, Any]) -> list[str]:
    label = f"binaries.{sha}"
    if not _SHA256_RE.match(str(sha)):
        return [f"{label}: key must be a lowercase 64-hex sha256"]
    if not isinstance(meta, Mapping):
        return [f"{label}: must be a mapping"]
    errors = []
    if meta.get("platform") not in PLATFORMS:
        errors.append(f"{label}.platform must be one of {PLATFORMS}")
    if not isinstance(meta.get("build"), str) or not meta["build"]:
        errors.append(f"{label}.build must be a non-empty NBER build stamp")
    if not _positive_int(meta.get("bytes")):
        errors.append(f"{label}.bytes must be a positive int")
    filename = meta.get("filename")
    if not isinstance(filename, str) or not filename or "/" in filename:
        errors.append(f"{label}.filename must be a bare file name")
    sources = meta.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append(f"{label}.sources must be a non-empty list")
        sources = []
    for index, source in enumerate(sources):
        errors.extend(_validate_source(f"{label}.sources[{index}]", source))
    for index, result in enumerate(meta.get("probe_results") or []):
        where = f"{label}.probe_results[{index}]"
        if not isinstance(result, Mapping) or result.get("probe") not in probes:
            errors.append(f"{where}.probe must name a declared probe")
            continue
        expect = result.get("expect")
        if not isinstance(expect, Mapping) or not expect or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in expect.values()
        ):
            errors.append(f"{where}.expect must map output columns to numbers")
        evidence = result.get("evidence")
        if (
            not isinstance(evidence, Mapping)
            or evidence.get("kind") not in _EVIDENCE_KINDS
            or not evidence.get("ref")
        ):
            errors.append(f"{where}.evidence needs kind {_EVIDENCE_KINDS} and ref")
    return errors


def _validate_source(label: str, source: Any) -> list[str]:
    if not isinstance(source, Mapping) or source.get("kind") not in _SOURCE_KINDS:
        return [f"{label}.kind must be one of {_SOURCE_KINDS}"]
    kind = source["kind"]
    errors = []
    if kind == "git":
        if not _REPO_RE.match(str(source.get("repo", ""))):
            errors.append(f"{label}.repo must be owner/name")
        if not _COMMIT_RE.match(str(source.get("commit", ""))):
            errors.append(f"{label}.commit must be a full 40-hex commit id")
        if not isinstance(source.get("path"), str) or not source["path"]:
            errors.append(f"{label}.path must be the blob path")
    elif kind == "url":
        if not str(source.get("url", "")).startswith("https://"):
            errors.append(f"{label}.url must be https")
        if not source.get("retrieved_on"):
            errors.append(f"{label}.retrieved_on is required")
    else:
        for key in ("package", "version", "filename", "member"):
            if not source.get(key):
                errors.append(f"{label}.{key} is required")
        if not _SHA256_RE.match(str(source.get("sha256", ""))):
            errors.append(f"{label}.sha256 must be the wheel's 64-hex sha256")
        if not _positive_int(source.get("bytes")):
            errors.append(f"{label}.bytes must be the wheel's size")
        if not str(source.get("url", "")).startswith("https://"):
            errors.append(f"{label}.url must be https")
    return errors


def _validate_profile(
    name: str, profile: Any, binaries: Mapping[str, Any]
) -> list[str]:
    label = f"profiles.{name}"
    if not isinstance(profile, Mapping):
        return [f"{label}: must be a mapping"]
    errors = []
    default = profile.get("binaries")
    if not isinstance(default, Mapping) or not default:
        return [f"{label}.binaries must map platforms to pinned sha256s"]
    errors.extend(_validate_platform_map(f"{label}.binaries", default, binaries))
    overrides = profile.get("overrides", [])
    if not isinstance(overrides, list):
        return [*errors, f"{label}.overrides must be a list"]
    seen_ids: set[str] = set()
    claimed: dict[tuple[int, int], str] = {}
    for index, override in enumerate(overrides):
        where = f"{label}.overrides[{index}]"
        if not isinstance(override, Mapping):
            errors.append(f"{where}: must be a mapping")
            continue
        override_id = override.get("id")
        if not isinstance(override_id, str) or not override_id:
            errors.append(f"{where}.id is required")
        elif override_id in seen_ids:
            errors.append(f"{where}.id {override_id!r} is duplicated")
        else:
            seen_ids.add(override_id)
        states = override.get("states")
        postal = override.get("state_postal")
        years = override.get("years")
        if not _int_list(states) or not all(
            code in _USPS_BY_TAXSIM_STATE for code in states
        ):
            errors.append(f"{where}.states must list TAXSIM SOI codes 1-51")
            states = []
        if not isinstance(postal, list) or len(postal) != len(states):
            errors.append(f"{where}.state_postal must parallel states")
        else:
            for code, usps in zip(states, postal, strict=True):
                if _USPS_BY_TAXSIM_STATE.get(code) != usps:
                    errors.append(
                        f"{where}: TAXSIM state {code} is "
                        f"{_USPS_BY_TAXSIM_STATE.get(code)!r}, not {usps!r}"
                    )
        if not _int_list(years):
            errors.append(f"{where}.years must list tax years")
            years = []
        override_binaries = override.get("binaries")
        if not isinstance(override_binaries, Mapping):
            errors.append(f"{where}.binaries must map platforms to sha256s")
        else:
            errors.extend(
                _validate_platform_map(f"{where}.binaries", override_binaries, binaries)
            )
            if set(override_binaries) != set(default):
                errors.append(
                    f"{where}.binaries must name the same platforms as the "
                    f"profile default ({sorted(default)})"
                )
        for key in ("reason", "linked_issue", "source"):
            if not isinstance(override.get(key), str) or not override[key]:
                errors.append(f"{where}.{key} is required")
        for state in states:
            for year in years:
                other = claimed.get((state, year))
                if other is not None:
                    errors.append(
                        f"{where}: (state {state}, year {year}) is already "
                        f"claimed by override {other!r}"
                    )
                claimed[(state, year)] = str(override_id)
    return errors


def _validate_platform_map(
    label: str, mapping: Mapping[str, Any], binaries: Mapping[str, Any]
) -> list[str]:
    errors = []
    for system, sha in mapping.items():
        if system not in PLATFORMS:
            errors.append(f"{label}: unknown platform {system!r}")
            continue
        meta = binaries.get(sha)
        if not isinstance(meta, Mapping):
            errors.append(f"{label}.{system}: {sha!r} is not a pinned binary")
        elif meta.get("platform") != system:
            errors.append(
                f"{label}.{system}: {sha} is pinned as a "
                f"{meta.get('platform')!r} binary"
            )
    return errors


@lru_cache(maxsize=1)
def pin_document() -> PinDocument:
    """Return the parsed pin document, failing closed when it is invalid."""
    return parse_pin_document(load_pins())


def parse_pin_document(doc: Mapping[str, Any]) -> PinDocument:
    """Validate and parse a raw pin document."""
    errors = validate_pin_document(doc)
    if errors:
        raise TaxsimPinError(
            "invalid TAXSIM pin document:\n  " + "\n  ".join(errors)
        )
    binaries = {
        sha: PinnedBinary(
            sha256=sha,
            platform=meta["platform"],
            build=meta["build"],
            bytes=int(meta["bytes"]),
            filename=meta["filename"],
            sources=tuple(meta["sources"]),
            probe_results=tuple(meta.get("probe_results") or ()),
        )
        for sha, meta in doc["binaries"].items()
    }
    profiles = {
        name: Profile(
            name=name,
            description=str(profile.get("description", "")),
            binaries=dict(profile["binaries"]),
            overrides=tuple(
                Override(
                    id=override["id"],
                    states=frozenset(override["states"]),
                    years=frozenset(override["years"]),
                    binaries=dict(override["binaries"]),
                )
                for override in profile.get("overrides", [])
            ),
        )
        for name, profile in doc["profiles"].items()
    }
    return PinDocument(
        default_profile=doc["default_profile"],
        binaries=binaries,
        profiles=profiles,
        probes=dict(doc.get("probes") or {}),
        raw=doc,
    )



# --------------------------------------------------------------------------
# Profile selection and resolution


def normalize_platform(system: str | None = None) -> str:
    """Return ``linux``/``darwin``/``windows`` for ``system`` (default: host)."""
    name = _host_platform(None if system == "current" else system)
    if name not in PLATFORMS:
        raise TaxsimPinError(
            f"no TAXSIM binaries are pinned for platform {name!r}; pinned "
            f"platforms: {', '.join(PLATFORMS)}"
        )
    return name


def profile_names() -> list[str]:
    return list(pin_document().profiles)


def get_profile(name: str) -> Profile:
    """Return a declared profile, or fail with the declared names."""
    profiles = pin_document().profiles
    if name not in profiles:
        raise TaxsimPinError(
            f"unknown TAXSIM pin profile {name!r}; declared profiles: "
            f"{', '.join(profiles)}"
        )
    return profiles[name]


def active_profile(
    explicit: str | None = None,
    suite_parameters: Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    """Return ``(profile name, where it came from)`` by the C4 precedence.

    Explicit argument / ``--taxsim-pin-profile`` > ``$AXIOM_TAXSIM_PIN_PROFILE``
    > the suite's ``runner.parameters.taxsim_pin_profile`` > the pin file's
    ``default_profile``. The chosen name is validated against the pin file.
    """
    suite_value = (suite_parameters or {}).get(SUITE_PROFILE_PARAMETER)
    for value, origin in (
        (explicit, "argument"),
        (os.environ.get(PROFILE_ENV), f"${PROFILE_ENV}"),
        (suite_value, f"suite parameter {SUITE_PROFILE_PARAMETER}"),
        (pin_document().default_profile, "default_profile"),
    ):
        if value:
            get_profile(str(value))
            return str(value), origin
    raise TaxsimPinError("no TAXSIM pin profile resolved")  # pragma: no cover


def active_profile_name(
    explicit: str | None = None,
    suite_parameters: Mapping[str, Any] | None = None,
) -> str:
    return active_profile(explicit, suite_parameters)[0]


def resolve_binary(
    state: Any,
    year: Any,
    system: str | None = None,
    profile: str | None = None,
) -> str:
    """Return the pinned sha256 for (state, year) on ``system`` under ``profile``."""
    return resolve(state, year, system, profile).sha256


def resolve(
    state: Any,
    year: Any,
    system: str | None = None,
    profile: str | None = None,
) -> Resolution:
    """Like :func:`resolve_binary`, also returning the override scope."""
    return get_profile(active_profile_name(profile)).resolve(state, year, system)


def pinned_binary(sha256: str) -> PinnedBinary:
    binaries = pin_document().binaries
    if sha256 not in binaries:
        raise TaxsimPinError(f"TAXSIM binary {sha256} is not pinned")
    return binaries[sha256]



_HASH_CACHE: dict[tuple[str, int, int], str] = {}


def cached_sha256(path: Path) -> str:
    """SHA-256 of ``path``, hashed once per process per (path, mtime, size)."""
    resolved = Path(path).resolve()
    stat = resolved.stat()
    key = (str(resolved), stat.st_mtime_ns, stat.st_size)
    digest = _HASH_CACHE.get(key)
    if digest is None:
        digest = sha256_file(resolved)
        _HASH_CACHE[key] = digest
    return digest


def clear_hash_cache() -> None:
    _HASH_CACHE.clear()


def cache_root() -> Path:
    """Root of the verified-binary cache (``$AXIOM_TAXSIM_CACHE_DIR``)."""
    configured = os.environ.get(CACHE_DIR_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_CACHE_DIR.expanduser()


def cache_path(sha256: str) -> Path:
    """Where the cache stores a pinned binary: ``<root>/<sha256>/<filename>``."""
    return cache_root() / sha256 / pinned_binary(sha256).filename


@dataclass(frozen=True)
class Candidate:
    """One place a pinned binary was looked for, and what was found there."""

    origin: str
    path: Path
    status: str  # "verified" | "missing" | "mismatch"
    observed_sha256: str | None = None
    observed_bytes: int | None = None


def binary_candidates(sha256: str) -> list[tuple[str, Path]]:
    """Every path checked for a pinned binary, in lookup order."""
    binary = pinned_binary(sha256)
    candidates: list[tuple[str, Path]] = []
    env_dir = os.environ.get(BINARY_DIR_ENV)
    if env_dir:
        root = Path(env_dir).expanduser()
        candidates.append((f"${BINARY_DIR_ENV}", root / sha256 / binary.filename))
        candidates.append((f"${BINARY_DIR_ENV}", root / binary.filename))
    candidates.append(("cache", cache_path(sha256)))
    try:
        host = normalize_platform()
    except TaxsimPinError:
        host = None
    if host == binary.platform:
        installed = installed_binary_path(binary.platform)
        if installed is not None:
            candidates.append(("installed policyengine-taxsim", installed))
    return candidates


def inspect_candidates(sha256: str) -> list[Candidate]:
    """Hash every candidate path for a pinned binary."""
    binary = pinned_binary(sha256)
    results = []
    for origin, path in binary_candidates(sha256):
        # Hash and return the absolute, symlink-resolved path. A relative
        # path (e.g. AXIOM_TAXSIM_BINARY_DIR=.) would otherwise be verified
        # here but looked up on PATH when executed, so a different
        # same-named executable could run under this binary's identity.
        path = path.resolve()
        if not path.is_file():
            results.append(Candidate(origin, path, "missing"))
            continue
        size = path.stat().st_size
        observed = cached_sha256(path)
        status = (
            "verified"
            if observed == sha256 and size == binary.bytes
            else "mismatch"
        )
        results.append(Candidate(origin, path, status, observed, size))
    return results


def find_verified_binary(sha256: str) -> Path | None:
    """The first candidate whose bytes match the pin, or None."""
    for candidate in inspect_candidates(sha256):
        if candidate.status == "verified":
            return candidate.path
    return None


def locate_binary(
    sha256: str,
    *,
    profile: str | None = None,
    state: Any = None,
    year: Any = None,
) -> Path:
    """Return verified bytes for a pinned binary, or raise TaxsimPinError.

    Lookup order: ``$AXIOM_TAXSIM_BINARY_DIR`` (``<dir>/<sha256>/<filename>``
    then ``<dir>/<filename>``), the cache (``$AXIOM_TAXSIM_CACHE_DIR`` or
    ``~/.cache/axiom-oracles/taxsim-binaries/<sha256>/<filename>``), then the
    installed policyengine-taxsim bundled executable for the host platform.
    A candidate is used only when its SHA-256 and size match the pin.
    """
    binary = pinned_binary(sha256)
    candidates = inspect_candidates(sha256)
    for candidate in candidates:
        if candidate.status == "verified":
            return candidate.path
    where = []
    for candidate in candidates:
        if candidate.status == "missing":
            where.append(f"    {candidate.origin}: {candidate.path} (absent)")
        else:
            where.append(
                f"    {candidate.origin}: {candidate.path} (sha256 "
                f"{candidate.observed_sha256}, {candidate.observed_bytes} bytes "
                "- does not match the pin)"
            )
    cell = ""
    if state is not None or year is not None:
        cell = f" for (state={state}, year={year})"
    profile_text = f" under profile {profile!r}" if profile else ""
    fetch = f"{FETCH_COMMAND} --platform {binary.platform}"
    if profile:
        fetch += f" --profile {profile}"
    raise TaxsimPinError(
        f"TAXSIM binary {sha256} ({binary.platform}, build {binary.build}) "
        f"required{profile_text}{cell} is not available as verified bytes.\n"
        "  Checked:\n" + "\n".join(where) + f"\n  Fetch it with: {fetch}"
    )



# --------------------------------------------------------------------------
# Fetching


Downloader = Callable[[str], bytes]


@dataclass(frozen=True)
class FetchResult:
    sha256: str
    path: Path
    status: str  # "present" | "fetched"
    source: str


def _http_download(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "axiom-oracles-taxsim-pin"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        return response.read()


def _git_blob(repo_path: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "cat-file", "blob", f"{commit}:{path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise TaxsimPinError(
            f"git cat-file {commit}:{path} failed in {repo_path}: "
            f"{result.stderr.decode(errors='replace').strip()} (run `git -C "
            f"{repo_path} fetch origin` if the commit is missing)"
        )
    return result.stdout


def _source_label(source: Mapping[str, Any]) -> str:
    kind = source["kind"]
    if kind == "git":
        return f"git {source['repo']}@{source['commit'][:12]}:{source['path']}"
    if kind == "url":
        return f"url {source['url']}"
    return f"wheel {source['filename']}!{source['member']}"


def _source_attempts(
    binary: PinnedBinary,
    from_git_repo: Path | None,
    download: Downloader,
) -> list[tuple[str, Callable[[], bytes]]]:
    attempts: list[tuple[str, Callable[[], bytes]]] = []
    git_sources = [s for s in binary.sources if s["kind"] == "git"]
    if from_git_repo is not None:
        for source in git_sources:
            attempts.append(
                (
                    f"local {from_git_repo}@{source['commit'][:12]}:{source['path']}",
                    lambda s=source: _git_blob(
                        from_git_repo, s["commit"], s["path"]
                    ),
                )
            )
    for source in git_sources:
        url = (
            f"https://raw.githubusercontent.com/{source['repo']}/"
            f"{source['commit']}/{source['path']}"
        )
        attempts.append((_source_label(source), lambda u=url: download(u)))
    for source in binary.sources:
        if source["kind"] == "url":
            attempts.append(
                (_source_label(source), lambda s=source: download(s["url"]))
            )
    for source in binary.sources:
        if source["kind"] == "wheel":
            attempts.append(
                (
                    _source_label(source),
                    lambda s=source: _wheel_member(s, download),
                )
            )
    return attempts


def _wheel_member(source: Mapping[str, Any], download: Downloader) -> bytes:
    wheel = download(source["url"])
    digest = hashlib.sha256(wheel).hexdigest()
    if digest != source["sha256"] or len(wheel) != int(source["bytes"]):
        raise TaxsimPinError(
            f"wheel {source['filename']} sha256 {digest} ({len(wheel)} bytes) "
            f"does not match the pinned {source['sha256']} ({source['bytes']})"
        )
    with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
        return archive.read(source["member"])


def verify_bytes(binary: PinnedBinary, data: bytes) -> str | None:
    """Return a mismatch description, or None when ``data`` matches the pin."""
    digest = hashlib.sha256(data).hexdigest()
    if digest != binary.sha256 or len(data) != binary.bytes:
        return f"got sha256 {digest} ({len(data)} bytes)"
    return None


def fetch_binary(
    sha256: str,
    *,
    from_git_repo: Path | None = None,
    download: Downloader | None = None,
    force: bool = False,
) -> FetchResult:
    """Place verified bytes for a pinned binary in the cache.

    Sources are tried in order: the local git repo (``from_git_repo``), the
    pinned git blobs via raw.githubusercontent.com, pinned URLs, then pinned
    wheels. Bytes are written (atomically, mode 0755) only after their
    SHA-256 and size match the pin; an unverified download never replaces a
    cache entry.
    """
    binary = pinned_binary(sha256)
    target = cache_path(sha256)
    if not force and target.is_file():
        if (
            target.stat().st_size == binary.bytes
            and cached_sha256(target) == sha256
        ):
            return FetchResult(sha256, target, "present", "cache")
    download = download or _http_download
    failures = []
    for label, fetch in _source_attempts(binary, from_git_repo, download):
        try:
            data = fetch()
        except Exception as exc:  # noqa: BLE001 - try the next pinned source
            failures.append(f"{label}: {exc}")
            continue
        mismatch = verify_bytes(binary, data)
        if mismatch is not None:
            failures.append(f"{label}: {mismatch}")
            continue
        _atomic_write_executable(target, data)
        return FetchResult(sha256, target, "fetched", label)
    raise TaxsimPinError(
        f"could not fetch verified bytes for TAXSIM binary {sha256} "
        f"({binary.platform}, build {binary.build}):\n  "
        + "\n  ".join(failures or ["no pinned sources"])
    )


def _atomic_write_executable(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".fetch-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp_name, 0o755)
        os.replace(tmp_name, target)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


# --------------------------------------------------------------------------
# Helpers


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _int_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
    )


def _integral(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise TaxsimPinError(f"TAXSIM {label} must be an integer, got {value!r}")
    if isinstance(value, int):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TaxsimPinError(
            f"TAXSIM {label} must be an integer, got {value!r}"
        ) from exc
    if not number.is_integer():
        raise TaxsimPinError(f"TAXSIM {label} must be an integer, got {value!r}")
    return int(number)


def taxsim_state_postal(code: int) -> str | None:
    """USPS code for a TAXSIM SOI state code (None for 0 / unknown)."""
    return _USPS_BY_TAXSIM_STATE.get(code)

