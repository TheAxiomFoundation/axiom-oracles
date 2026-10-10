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

The per-platform executables in one release are different NBER builds with
different law-year ranges (each bundled binary's ``law_years`` in the pin
file), so the platform decides which law years can run.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from collections.abc import Iterable
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

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
    return _bare_stamp(left) == _bare_stamp(right)


def _bare_stamp(stamp: str) -> str:
    stamp = stamp.strip().strip('"')
    if stamp.startswith("cdate-"):
        return stamp[len("cdate-") :]
    if re.fullmatch(r"cd\d{10}", stamp):
        return stamp[2:]
    return stamp


def pinned_entry_for_sha(sha256: str) -> tuple[str, dict[str, Any]] | None:
    """Return ``(key, entry)`` of the bundled binary pinned with ``sha256``."""
    for key, entry in bundled_binaries().items():
        if entry["sha256"] == sha256:
            return key, dict(entry)
    return None


def law_year_range(entry: dict[str, Any] | None) -> tuple[int, int] | None:
    """Return the ``(first, last)`` law years a pinned binary was run on.

    ``None`` when the binary has not been executed (its range is unknown).
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
    and no ``binary_path``) the installed one for ``system`` (default: this
    host), else the pinned binary for ``system`` (what the ``taxsim`` extra
    installs). A binary the pin does not record, or whose range is unknown,
    is not checked. Returns the identity of the existing binary that was
    resolved, else ``None``.

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
        path = installed_binary_path(system)
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
        f"TAXSIM cannot run {noun} {shown} on {system}: the binary "
        f"policyengine-taxsim {pinned_version()} uses here ({where}, sha256 "
        f"{entry['sha256'][:12]}, build {entry.get('build')}) accepts law years "
        f"{first}-{last} only."
    )
    rejection = (entry.get("law_years") or {}).get("rejection")
    if rejection:
        message += (
            f" Run on law years outside that range, it printed "
            f"{rejection.strip()!r} and exited 1."
        )
    alternatives = [
        f"{other_system} ({other_key}, build "
        f"{bundled_binaries()[other_key].get('build')}, "
        f"{other_range[0]}-{other_range[1]})"
        for other_system, other_key in load_pins()["runtime_binary"][
            "by_platform"
        ].items()
        if other_system != system
        and (other_range := law_year_range(bundled_binaries()[other_key]))
        and all(other_range[0] <= year <= other_range[1] for year in rejected)
    ]
    if alternatives:
        message += (
            f" The pinned binary for {' and '.join(alternatives)} accepts "
            f"{shown}: run there, or use a law year in {first}-{last}."
        )
    else:
        message += (
            f" No pinned binary accepts {shown}; use a law year in "
            f"{first}-{last}."
        )
    return f"{message} (Pinned ranges: axiom_oracles/adapters/taxsim/taxsim_pins.json.)"


class TaxsimIdentityRecorder:
    """Accumulate the identity of every TAXSIM binary a run executes.

    ``observe`` hashes each binary once per path, counts the input rows it
    was given, and keeps the build stamp its output printed. A printed stamp
    that names a different build than the hashed bytes, or a ``sha256``
    (the hash taken before a batch ran) that differs from the recorded one,
    raises :class:`TaxsimIdentityError`: the hashed file is not what ran.
    """

    def __init__(self) -> None:
        self._identities: dict[str, dict[str, Any]] = {}
        self._rows: dict[str, int] = {}
        self._observed: dict[str, str | None] = {}

    def observe(
        self,
        path: Path,
        *,
        rows: int,
        build_observed: str | None = None,
        sha256: str | None = None,
    ) -> dict[str, Any]:
        key = str(path)
        identity = self._identities.get(key)
        if identity is None:
            identity = binary_identity(Path(path))
            self._identities[key] = identity
            self._rows[key] = 0
            self._observed[key] = None
        if sha256 is not None and sha256 != identity["sha256"]:
            raise TaxsimIdentityError(
                f"TAXSIM binary {path} changed during the run: sha256 "
                f"{sha256[:12]} before a batch, {identity['sha256'][:12]} "
                "recorded"
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
            previous = self._observed[key]
            if previous is not None and previous != build_observed:
                raise TaxsimIdentityError(
                    f"TAXSIM binary {path} printed build {previous!r} and "
                    f"later {build_observed!r} in one run"
                )
            self._observed[key] = build_observed
        self._rows[key] += int(rows)
        return identity

    def binaries(self) -> list[dict[str, Any]]:
        return [
            {
                **identity,
                "build_observed": self._observed[key],
                "rows": self._rows[key],
            }
            for key, identity in self._identities.items()
        ]

    def to_dict(self) -> dict[str, Any] | None:
        """The ``engine_identity.taxsim`` block, or ``None`` before any run."""
        if not self._identities:
            return None
        return {
            "pinned_policyengine_taxsim": pinned_version(),
            "binaries": self.binaries(),
        }
