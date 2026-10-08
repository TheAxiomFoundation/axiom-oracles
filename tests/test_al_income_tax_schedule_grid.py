"""Focused invariants for Alabama's canonical schedule-grid checker."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_checker():
    path = (
        Path(__file__).parents[1]
        / "scripts"
        / "check_al_income_tax_schedule_grid.py"
    )
    spec = importlib.util.spec_from_file_location("al_schedule_grid", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_path_pins_canonical_module(tmp_path):
    checker = _load_checker()
    assert checker.fixture_path(tmp_path) == (
        tmp_path
        / "us-al"
        / "policies"
        / "income_tax"
        / "2026_section_40_18_5_schedule_before_credits.test.yaml"
    )
    assert "liability" not in checker.MODULE
