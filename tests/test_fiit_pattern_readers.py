"""FIIT's child-concept patterns count compared mismatches, including old rows."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.bridges import tax_populace
from tests.test_native_fiit_missing_returns import Frame, runner

ROOT = Path(__file__).resolve().parents[1]
BUN = shutil.which("bun")
pytestmark = pytest.mark.skipif(BUN is None, reason="dashboard patterns require Bun")


def fiit_report(pairs):
    """Run the native FIIT producer and adapter; retain their actual hierarchy."""
    surface = "employee-medicare"
    specs = tax_populace.SURFACE_OUTPUTS[surface]
    output = next(iter(specs.values()))
    pe_rows = [{spec["pe"]: 0 for spec in specs.values()} for _ in pairs]
    results = [{"outputs": {
        spec["axiom"]: {"kind": "quantity", "value": {"value": 0}}
        for spec in specs.values()
    }} for _ in pairs]
    for index, (left, right) in enumerate(pairs):
        pe_rows[index][output["pe"]] = right
        results[index]["outputs"][output["axiom"]]["value"]["value"] = left
    raw = tax_populace.compare_outputs(
        pe_data={"tax_units": Frame(pe_rows), "persons": Frame(pe_rows),
                 "tax_unit_ids": list(range(len(pairs))),
                 "person_ids": list(range(len(pairs)))},
        axiom_outputs_by_surface={surface: results}, tolerance=0, relative_tolerance=0,
    ).to_json()
    report = runner()._adapt_tax_ecps_to_v2(
        json.loads(json.dumps(raw, allow_nan=False)), {}, suite="fiit-ecps",
    )
    return report


PATTERNS = r"""
import { readFileSync } from "node:fs";
import * as suites from "./dashboard/src/utils/suites.js";
import { comparedMismatchCount } from "./dashboard/src/utils/caseMismatches.mjs";
import { causeFor } from "./dashboard/src/utils/programs.js";
const deps = { ...suites, comparedMismatchCount, causeFor };
function loadCountingFunction(file, begin, end, finish) {
  const source = readFileSync(file, "utf8");
  const start = source.indexOf(begin);
  if (start < 0) throw new Error(`Missing counting function: ${begin}`);
  const stop = source.indexOf(end, start);
  if (stop < 0) throw new Error(`Missing counting boundary: ${end}`);
  return new Function(...Object.keys(deps),
    source.slice(start, stop) + finish)(...Object.values(deps));
}
const ledger = loadCountingFunction(
  "dashboard/src/components/OraclesV2.jsx", "function buildClasses(",
  "\nfunction ActionChip(", "; return buildClasses;",
);
// Execute WhySection's complete counting prefix, before its JSX rendering.
const program = loadCountingFunction(
  "dashboard/src/components/ProgramPage.jsx", "function WhySection(",
  "\n  if (!rows.length)", "\nreturn {rows, trueTotal}; } return WhySection;",
);
const reports = await new Response(Bun.stdin.stream()).json();
console.log(JSON.stringify(reports.map(report => ({
  metric: suites.reportMetric(report),
  topLevelCount: suites.topLevelAggregates(report.aggregates).length,
  ledger: ledger([report], []).map(({concept, kind, count}) => ({concept, kind, count})),
  program: program({programReports: [report], knownCauses: []}),
}))));
"""


def read_patterns(*reports):
    result = subprocess.run(
        [BUN, "-e", PATTERNS], cwd=ROOT, input=json.dumps(reports),
        capture_output=True, text=True, check=True, timeout=30,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("reader", ["ledger", "program"])
def test_fiit_child_patterns_exclude_engine_errors_without_row_flags(reader):
    report = fiit_report([(0, 50), (0, None)])
    # Historical published FIIT rows lack this flag; keep testing that fallback
    # after the native producer starts carrying comparison status.
    for row in report["mismatches"]:
        row.pop("uncompared", None)
    assert all("uncompared" not in row for row in report["mismatches"])
    [result] = read_patterns(report)
    assert len(report["aggregates"]) == 2
    assert result["topLevelCount"] == 1
    assert result["metric"]["total"] == result["metric"]["mismatches"] == 1
    assert result["metric"]["uncompared"] == 1
    rows = result[reader] if reader == "ledger" else result[reader]["rows"]
    assert [(row["concept"], row["kind"], row["count"]) for row in rows] == [
        (report["mismatches"][0]["concept"], "amount_difference", 1),
    ]


@pytest.mark.parametrize("reader", ["ledger", "program"])
@pytest.mark.parametrize("with_row_flags", [False, True])
def test_fiit_engine_errors_alone_do_not_create_a_disagreement_pattern(reader, with_row_flags):
    report = fiit_report([(0, None)])
    if not with_row_flags:
        for row in report["mismatches"]:
            row.pop("uncompared", None)
    [result] = read_patterns(report)
    rows = result[reader] if reader == "ledger" else result[reader]["rows"]
    assert rows == []


@pytest.mark.parametrize("reader", ["ledger", "program"])
@pytest.mark.parametrize("include_field,expected", [(False, 1), (True, 2)])
def test_fiit_truncated_child_pattern_preserves_legacy_fallback(reader, include_field, expected):
    report = fiit_report([(0, 50), (0, 100)])
    if not include_field:
        for aggregate in report["aggregates"]:
            aggregate.pop("uncompared_mismatches")
    # The old truncated report used the retained child row as its pattern count.
    report["mismatches"] = report["mismatches"][:1]
    [result] = read_patterns(report)
    rows = result[reader] if reader == "ledger" else result[reader]["rows"]
    assert result["metric"]["mismatches"] == 2
    assert len(rows) == 1
    assert rows[0]["count"] == expected


@pytest.mark.parametrize("reader", ["ledger", "program"])
def test_committed_fiit_patterns_use_complete_compared_child_counts(reader):
    """A single-kind child uses its full aggregate, even when the list is slimmed."""
    report = json.loads(
        (ROOT / "dashboard/public/data/axiom-policyengine-fiit-ecps.json").read_text()
    )
    prefix = "us:tax/federal-income-tax#"
    expected = {
        f"{prefix}eitc": 17_424,
        f"{prefix}tax_before_credits": 2_118,
        f"{prefix}capital_gain": 8,
        f"{prefix}ctc": 5,
    }
    retained = {
        concept: sum(row["concept"] == concept for row in report["mismatches"])
        for concept in expected
    }
    assert retained[f"{prefix}eitc"] == 367
    assert retained[f"{prefix}tax_before_credits"] == 620
    assert len(report["mismatches"]) == 1_000
    aggregates = {aggregate["concept"]: aggregate for aggregate in report["aggregates"]}
    for concept, count in expected.items():
        aggregate = aggregates[concept]
        assert aggregate["parent"] == f"{prefix}liability"
        assert aggregate["mismatch_count"] - aggregate["uncompared_mismatches"] == count

    [result] = read_patterns(report)
    rows = result[reader] if reader == "ledger" else result[reader]["rows"]
    assert {(row["concept"], row["kind"]): row["count"] for row in rows} == {
        (concept, "amount_difference"): count for concept, count in expected.items()
    }
    # The parent is the run total; counting it as another pattern would double
    # the children. Each child occurs once, and together they equal that total.
    assert len(rows) == len(expected)
    assert sum(row["count"] for row in rows) == result["metric"]["mismatches"] == 19_555
    assert result["topLevelCount"] == 1


@settings(max_examples=12, deadline=None, derandomize=True)
@given(
    compared=st.lists(st.integers(-100, 100), min_size=1, max_size=5),
    uncompared=st.integers(1, 5),
)
def test_property_fiit_pattern_counts_ignore_added_engine_errors(compared, uncompared):
    """A FIIT child pattern equals its compared mismatch count, independent of errors."""
    pairs = [(0, right) for right in compared]
    clean, errored = read_patterns(
        fiit_report(pairs), fiit_report(pairs + [(0, None)] * uncompared),
    )
    expected = sum(right != 0 for right in compared)
    for result in (clean, errored):
        assert sum(row["count"] for row in result["ledger"]) == expected
        assert sum(row["count"] for row in result["program"]["rows"]) == expected
        assert all(row["count"] > 0 for row in result["ledger"])
        assert all(row["count"] > 0 for row in result["program"]["rows"])
    assert clean["ledger"] == errored["ledger"]
    assert clean["program"]["rows"] == errored["program"]["rows"]
