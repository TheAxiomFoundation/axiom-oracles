"""Focused invariants for the state income-tax comparison generator."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_generator():
    path = (
        Path(__file__).parents[1]
        / "scripts"
        / "generate_state_income_tax_liability.py"
    )
    spec = importlib.util.spec_from_file_location("state_income_tax_generator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_summary_counts_both_pairwise_legs_regardless_of_pe_match_status():
    generator = _load_generator()
    cases = [
        generator.Case("dc-single-30000", "DC", "single", 30_000.0),
        generator.Case("dc-married-60000", "DC", "married", 60_000.0),
    ]
    axiom = {
        ("DC", "single", 30_000): 1_000.0,
        ("DC", "married", 60_000): 2_000.0,
    }
    taxsim = {case.case_id: 0.0 for case in cases}

    for policyengine in (
        {"dc-single-30000": 1_000.0, "dc-married-60000": 2_000.0},
        {"dc-single-30000": 900.0, "dc-married-60000": 2_000.0},
    ):
        summary = generator._build_report(
            "DC", cases, axiom, policyengine, taxsim
        )["summary"]
        assert summary["comparison_count"] == 4
        assert summary["match_count"] + summary["mismatch_count"] == 4


def test_committed_state_income_tax_reports_are_dispositioned_v21():
    reports = (
        Path(__file__).parents[1] / "dashboard" / "public" / "data"
    ).glob("axiom-policyengine-taxsim-*-income-tax-liability.json")

    for path in reports:
        report = json.loads(path.read_text())
        assert report["schema_version"] == "axiom.comparison_report.v2.1", path
        assert isinstance(report["summary"].get("dispositioned"), dict), path
