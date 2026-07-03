"""Loader and hashing helpers for the pinned TAXSIM binary identity.

The axiom-oracles TAXSIM adapter shells out to a TAXSIM executable bundled
inside the ``policyengine-taxsim`` distribution (see ``runner.py``, which
imports ``TaxsimRunner`` dynamically). That binary is not vendored in this
repository, so reproducibility is pinned indirectly: ``taxsim_pins.json``
records the exact ``policyengine-taxsim`` release, its PyPI artifact hashes,
and the SHA-256 of each bundled executable.

This module reads that pin file and provides utilities to (a) resolve the
binary path an installed ``policyengine-taxsim`` would use and (b) recompute
its hash so a test can confirm the installed binary still matches the pin.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

PINS_PATH = Path(__file__).resolve().parent / "taxsim_pins.json"

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
    """Return the mapping of bundled-binary relative path -> {sha256, bytes}."""
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

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None
