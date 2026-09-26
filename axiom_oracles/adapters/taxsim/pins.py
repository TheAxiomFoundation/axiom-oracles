"""Pinned TAXSIM binary identity: profiles, resolution, and the runtime check.

``taxsim_pins.json`` (schema ``axiom-oracles/taxsim-pin/v2``) pins every NBER
TAXSIM executable the adapter may run by SHA-256 and byte size, and groups
them into named *profiles*. A profile maps each (TAXSIM SOI state, tax year)
to one pinned binary per platform: a profile default plus declarative
overrides (e.g. Georgia and Maryland 2024-2025 in ``dashboard-2026-09``).

This module:

* loads and validates the pin document (:func:`validate_pin_document`);
* selects the active profile (:func:`active_profile`, precedence: explicit
  argument or ``--taxsim-pin-profile`` > ``$AXIOM_TAXSIM_PIN_PROFILE`` >
  a suite's ``runner.parameters.taxsim_pin_profile`` > ``default_profile``);
* resolves the pinned SHA-256 for a row (:func:`resolve_binary`);
* finds verified bytes for a pinned SHA-256 (:func:`locate_binary`): every
  candidate path is hashed and only an exact SHA-256 + size match is
  returned, otherwise :class:`TaxsimPinError` names the SHA, profile,
  (state, year) and the fetch command;
* fetches pinned binaries into the cache (:func:`fetch_binary`), writing
  only bytes that verified.

The ``policyengine-taxsim`` package pin (``distribution``) is separate: it
supplies the Python wrapper and the PolicyEngine emulator, and records the
executables its wheel bundles for callers that still run those directly.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform as _platform
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .projection import _TAXSIM_STATE_CODES

PINS_PATH = Path(__file__).resolve().parent / "taxsim_pins.json"
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
# The build stamp a TAXSIM executable writes as its last output header column:
# "cdate-<stamp>" through build 20260521, "cd<YYYYMMDDHH>" in later builds.
# Normalized like policyengine-taxsim's TaxsimRunner (strip "cdate-").
_BUILD_STAMP_RE = re.compile(
    rb"cdate-([A-Za-z0-9]+)|(?<![0-9A-Za-z])(cd20\d{8})(?![0-9])"
)
_USPS_BY_TAXSIM_STATE = {code: usps for usps, code in _TAXSIM_STATE_CODES.items()}

# Platform -> bundled-binary key in the distribution block. Mirrors
# policyengine_taxsim.runners.taxsim_runner._detect_taxsim_executable.
_PLATFORM_BINARY_KEY = {
    "linux": "taxsimtest/taxsimtest-linux.exe",
    "darwin": "taxsimtest/taxsimtest-osx.exe",
    "windows": "taxsimtest/taxsimtest-windows.exe",
}


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


# --------------------------------------------------------------------------
# Loading and validation


@lru_cache(maxsize=1)
def load_pins() -> dict[str, Any]:
    """Return the raw TAXSIM pin document."""
    return json.loads(PINS_PATH.read_text())


def validate_pin_document(doc: Mapping[str, Any]) -> list[str]:
    """Return every structural or consistency error in a v2 pin document."""
    errors: list[str] = []
    if doc.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION!r}, got "
            f"{doc.get('schema_version')!r}"
        )
    errors.extend(_validate_distribution(doc.get("distribution")))
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
    bundled = dist.get("bundled_binaries")
    if not isinstance(bundled, Mapping) or not bundled:
        errors.append("distribution.bundled_binaries must be a non-empty mapping")
    else:
        for key, meta in bundled.items():
            if not str(key).endswith(".exe"):
                errors.append(f"distribution.bundled_binaries key {key!r}")
            if not isinstance(meta, Mapping) or not _SHA256_RE.match(
                str(meta.get("sha256", ""))
            ):
                errors.append(f"distribution.bundled_binaries.{key}.sha256")
            elif not _positive_int(meta.get("bytes")):
                errors.append(f"distribution.bundled_binaries.{key}.bytes")
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
# Package pin (policyengine-taxsim distribution)


def pinned_version() -> str:
    """Return the pinned ``policyengine-taxsim`` version."""
    return str(load_pins()["distribution"]["version"])


def bundled_binaries() -> dict[str, dict[str, Any]]:
    """Return the pinned wheel's bundled-binary path -> {sha256, bytes}."""
    return dict(load_pins()["distribution"]["bundled_binaries"])


def platform_binary_key(system: str | None = None) -> str | None:
    """Return the pinned wheel's bundled-binary key for ``system``."""
    key = (system or _platform.system()).lower()
    return _PLATFORM_BINARY_KEY.get(key)


# --------------------------------------------------------------------------
# Profile selection and resolution


def normalize_platform(system: str | None = None) -> str:
    """Return ``linux``/``darwin``/``windows`` for ``system`` (default: host)."""
    name = (system or _platform.system()).lower()
    if name == "current":
        name = _platform.system().lower()
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


# --------------------------------------------------------------------------
# Hashing, build stamps, and locating verified bytes


_HASH_CACHE: dict[tuple[str, int, int], str] = {}


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's bytes."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def build_stamp_from_bytes(data: bytes) -> str | None:
    """The build stamp a TAXSIM executable embeds, normalized, or None."""
    match = _BUILD_STAMP_RE.search(data)
    if match is None:
        return None
    return (match.group(1) or match.group(2)).decode("ascii")


def read_build_stamp(path: Path) -> str | None:
    """Read the embedded build stamp from an executable's bytes."""
    return build_stamp_from_bytes(Path(path).read_bytes())


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


def installed_binary_path(system: str | None = None) -> Path | None:
    """Return the installed policyengine-taxsim bundled binary for ``system``.

    Searches the ``policyengine-taxsim`` data-file install locations its
    runner uses. Returns ``None`` when the package is not installed. The
    returned bytes are unverified; the pinned lookup hashes them.
    """
    system = (system or _platform.system()).lower()
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
