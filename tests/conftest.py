"""Suite-wide test fixtures."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from axiom_oracles import pinned_artifacts


@pytest.fixture
def pin_taxsim_stand_in(monkeypatch) -> Callable[..., str]:
    """Pin a stand-in TAXSIM executable as the default profile's only binary.

    The default TAXSIM runner executes only bytes whose SHA-256 and size equal
    a pin profile's binary. Tests that run a shell script in place of
    taxsimtest call ``pin_taxsim_stand_in(path)``: it adds the script's hash
    to a copy of the pin document under a profile named ``stand-in``, makes
    that profile the default for the host platform, and points
    ``$AXIOM_TAXSIM_BINARY_DIR`` at the script's directory. Returns the
    pinned SHA-256. ``law_years`` gives the stand-in a pinned law-year range.
    """
    from axiom_oracles.adapters.taxsim import pins

    original = copy.deepcopy(pins.load_pins())

    def pin(
        binary: Path,
        *,
        system: str | None = None,
        law_years: dict | None = None,
        build: str | None = None,
    ) -> str:
        binary = Path(binary)
        system = pins.normalize_platform(system)
        data = binary.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        doc = copy.deepcopy(original)
        entry = {
            "platform": system,
            "build": build or pins.build_stamp_from_bytes(data) or "stand-in",
            "bytes": len(data),
            "filename": binary.name,
            "sources": [
                {
                    "kind": "url",
                    "url": "https://example.invalid/taxsim-stand-in",
                    "retrieved_on": "2026-11-02",
                }
            ],
        }
        if law_years is not None:
            entry["law_years"] = law_years
        doc["binaries"][sha] = entry
        doc["profiles"]["stand-in"] = {
            "description": "A test stand-in for taxsimtest.",
            "binaries": {system: sha},
            "overrides": [],
        }
        doc["default_profile"] = "stand-in"
        parsed = pins.parse_pin_document(doc)
        monkeypatch.setattr(pins, "load_pins", lambda: doc)
        monkeypatch.setattr(pins, "pin_document", lambda: parsed)
        monkeypatch.setenv(pins.BINARY_DIR_ENV, str(binary.parent.resolve()))
        monkeypatch.delenv(pins.PROFILE_ENV, raising=False)
        pins.clear_hash_cache()
        return sha

    return pin


@pytest.fixture(autouse=True)
def _offline_pinned_artifacts(monkeypatch, tmp_path_factory):
    """Resolve pruned PolicyEngine pins without downloading them.

    Command-building tests reach axiom_oracles.pinned_artifacts.requirement
    for the default oracle pins; the real fetch downloads a 13 MB wheel. Point
    the cache at a per-session directory and return the path the verified
    file would have. tests/test_pinned_artifacts.py exercises the real fetch.
    """
    monkeypatch.setenv(
        pinned_artifacts.CACHE_ENV,
        str(tmp_path_factory.getbasetemp() / "pinned-artifacts"),
    )
    monkeypatch.setattr(pinned_artifacts, "fetch", pinned_artifacts.cache_path)
