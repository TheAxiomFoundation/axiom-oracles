"""Suite-wide test fixtures."""

from __future__ import annotations

import pytest

from axiom_oracles import pinned_artifacts


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
