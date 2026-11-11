"""Summary readers floor compared mismatches and disclose engine failures."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
from functools import cache
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_uncompared_mismatch_readers import (
    load_runner,
    workflow_summary_snippet,
)


@cache
def summary_runner():
    return load_runner()


def runner_summary(tmp_path, data):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data))
    with redirect_stdout(io.StringIO()) as captured:
        summary_runner()._print_summary(path)
    return captured.getvalue()


def test_runner_summary_floors_malformed_headline_before_oracle_divergences(tmp_path):
    out = runner_summary(tmp_path, {
        "compared_values": 3,
        "mismatch_count": 1,
        "uncompared_mismatches": 2,
        "oracle_divergence_count": 1,
    })
    assert "Mismatches:        0\n" in out
    assert "Differences:       1\n" in out
    assert "Agreement:         66.6667%" in out


def test_runner_summary_floors_each_surface_before_oracle_divergences(tmp_path):
    out = runner_summary(tmp_path, {
        "compared_values": 3,
        "mismatch_count": 1,
        "output_summary": [{
            "surface": "probe", "compared": 3, "mismatches": 1,
            "uncompared_mismatches": 2, "oracle_divergences": 1,
        }],
    })
    assert "2/3 ( 66.67%)  differences=1" in out


def test_runner_case_aggregate_floors_malformed_mismatches(tmp_path):
    out = runner_summary(tmp_path, {
        "case_count": 3,
        "aggregates": [{
            "concept": "probe", "comparison_count": 3, "mismatch_count": 1,
            "uncompared_mismatches": 2,
        }],
    })
    assert "compared=3  matched=3  uncompared=2" in out


def variable_report(kind, mismatches, uncompared):
    from axiom_oracles.bridges import tax_populace as tax_microcosm, us_populace as us_microcosm

    output = {
        "surface": "probe", "output": "amount", "compared": 5,
        "mismatches": mismatches, "uncompared_mismatches": uncompared,
        "max_abs_diff": 0.0, "max_relative_diff": 0.0,
    }
    values = dict(
        entity_id="1", output="amount", axiom=0.0, policyengine=1.0, diff=1.0,
    )
    common = dict(
        compared_persons=1, compared_values=5, output_summary=[output],
        projection_notes=[],
    )
    if kind == "fiit":
        row = tax_microcosm.TaxComparisonRow(surface="probe", **values)
        report = tax_microcosm.TaxComparisonReport(
            compared_tax_units=1, mismatches=[row] * mismatches, **common,
        )
        printer, options = tax_microcosm.print_report, {}
    else:
        row = us_microcosm.USVariableComparisonRow(variable="probe", **values)
        report = us_microcosm.USVariableComparisonReport(
            variables=("probe",), compared_spm_units=1, skipped_cases=0,
            skipped_reasons={}, mismatches=[row] * mismatches, **common,
        )
        printer, options = us_microcosm.print_report, {"max_differences": 0}
    with redirect_stdout(io.StringIO()) as captured:
        printer(report, tolerance=0.01, relative_tolerance=0, **options)
    return captured.getvalue()


@pytest.mark.parametrize("kind", ["fiit", "us"])
def test_native_summary_floors_malformed_headline(kind):
    out = variable_report(kind, mismatches=1, uncompared=2)
    assert "Mismatches: 0\n" in out


@pytest.mark.parametrize("kind", ["fiit", "us"])
def test_native_summary_floors_malformed_output(kind):
    out = variable_report(kind, mismatches=1, uncompared=2)
    assert "0/5 mismatch" in out


@pytest.mark.parametrize("kind", ["fiit", "us"])
@settings(max_examples=20, deadline=None, derandomize=True)
@given(mismatches=st.integers(0, 5), uncompared=st.integers(0, 10))
def test_property_native_summary_compared_mismatches_are_floored(kind, mismatches, uncompared):
    expected = max(0, mismatches - uncompared)
    out = variable_report(kind, mismatches, uncompared)
    assert f"Mismatches: {expected}\n" in out
    assert f"{expected}/5 mismatch" in out


def test_workflow_summary_floors_malformed_mismatches(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "compared_values": 3, "mismatch_count": 1, "uncompared_mismatches": 2,
    }))
    out = subprocess.run(
        [sys.executable, "-c", workflow_summary_snippet().replace("$latest", str(path))],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "mismatch_count:  0\n" in out
    assert "agreement:       100.0000%" in out


def test_workflow_summary_preserves_case_count_output(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"case_count": 3, "cases": [{"mismatches": [{}]}]}))
    out = subprocess.run(
        [sys.executable, "-c", workflow_summary_snippet().replace("$latest", str(path))],
        capture_output=True, text=True, check=True,
    ).stdout
    assert out == "cases:            3\nmismatch_entries: 1\n"


@pytest.mark.parametrize("with_summary", [False, True])
def test_runner_case_summary_discloses_uncompared_pairs_and_errors(tmp_path, with_summary):
    data = {
        "case_count": 3,
        "errors": [{"engine": "axiom"}] * 3,
        "aggregates": [
            {"concept": "parent", "parent": None, "uncompared_mismatches": 2},
            {"concept": "child", "parent": "parent", "uncompared_mismatches": 2},
        ],
    }
    if with_summary:
        data["summary"] = {"uncompared_mismatches": 2, "error_count": 3}
    out = runner_summary(tmp_path, data)
    assert "Uncompared:        2 (engine errors: 3)" in out


def test_runner_case_summary_uses_published_error_count_without_error_rows(tmp_path):
    out = runner_summary(tmp_path, {
        "case_count": 3,
        "summary": {"uncompared_mismatches": 2, "error_count": 3},
    })
    assert "Uncompared:        2 (engine errors: 3)" in out


@settings(max_examples=20, deadline=None, derandomize=True)
@given(pairs=st.lists(st.integers(0, 10), min_size=1, max_size=4))
def test_property_runner_case_summary_counts_each_uncompared_pair_once(pairs):
    rows = []
    for index, uncompared in enumerate(pairs):
        rows.extend([
            {"concept": f"parent-{index}", "uncompared_mismatches": uncompared},
            {"concept": f"child-{index}", "parent": f"parent-{index}",
             "uncompared_mismatches": uncompared},
        ])
    data = {"case_count": 3, "aggregates": rows, "errors": [{}] * sum(pairs)}
    path = SimpleNamespace(read_text=lambda: json.dumps(data))
    with redirect_stdout(io.StringIO()) as captured:
        summary_runner()._print_summary(path)
    out = captured.getvalue()
    if sum(pairs):
        assert f"Uncompared:        {sum(pairs)} (engine errors: {sum(pairs)})" in out
    else:
        assert "Uncompared:" not in out


def test_runner_case_summary_preserves_legacy_output(tmp_path):
    out = runner_summary(tmp_path, {
        "case_count": 3,
        "aggregates": [{"concept": "probe", "comparison_count": 3, "mismatch_count": 1}],
    })
    assert out == (
        "\nCases:             3\nMismatch entries:  0\n\n"
        f"  {'probe':40s}  compared=3  matched=2\n"
    )
