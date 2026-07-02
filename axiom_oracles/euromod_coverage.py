"""Static EUROMOD coverage inventories shipped with axiom-oracles."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


def load_belgium_coverage() -> dict[str, Any]:
    """Return the pinned EUROMOD Belgium BE_2025 coverage inventory."""
    payload = (
        resources.files("axiom_oracles.data")
        .joinpath("euromod_be_coverage.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(payload)


def load_euromod_issues() -> dict[str, Any]:
    """Return logged EUROMOD-platform bugs and oracle workarounds."""
    payload = (
        resources.files("axiom_oracles.data")
        .joinpath("euromod_issues.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(payload)
