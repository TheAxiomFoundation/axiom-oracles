"""Readers of ``mismatch_count`` leave uncompared pairs out of agreement (#668).

Several producers write a ``mismatch_count`` that includes uncompared pairs:
pairs where one engine's return was missing or nonfinite, recorded as an
engine error and counted in ``uncompared_mismatches``. ``comparison_count``,
``compared_values`` and ``mismatch_weight`` exclude them. Every reader that
pairs ``mismatch_count`` with a compared count must subtract the uncompared
pairs first, and show them as a separate figure.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
BUN = shutil.which("bun")
needs_bun = pytest.mark.skipif(BUN is None, reason="dashboard helpers require Bun")

CONCEPT = "us:test/program#benefit"


def aggregate(compared, mismatched, uncompared, concept=CONCEPT):
    """An aggregate as the SNAP adapter, FIIT and the shard merge write it."""
    return {
        "concept": concept,
        "parent": None,
        "comparison_count": compared,
        "match_count": compared - mismatched,
        "mismatch_count": mismatched + uncompared,
        "mismatch_weight": mismatched,
        "uncompared_mismatches": uncompared,
        "match_rate": (compared - mismatched) / compared * 100 if compared else 100.0,
    }


def run_bun(script: str, payload) -> object:
    result = subprocess.run(
        [BUN, "-e", script],
        cwd=ROOT,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return json.loads(result.stdout)


METRIC = """
import { reportMetric } from "./dashboard/src/utils/suites.js";
import { buildNWayData } from "./dashboard/src/utils/data.js";
const reports = await new Response(Bun.stdin.stream()).json();
console.log(JSON.stringify(reports.map((report) => ({
  metric: reportMetric(report),
  summary: buildNWayData([report]).summary,
}))));
"""


def report_of(*aggregates):
    return {
        "suite": "verdict-probe",
        "engines": {"left": "axiom", "right": "policyengine"},
        "concepts": [{"id": agg["concept"]} for agg in aggregates],
        "aggregates": list(aggregates),
        "cases": [],
    }


# ── the issue's example ──────────────────────────────────────────────────────
@needs_bun
def test_report_metric_leaves_uncompared_pairs_out_of_the_headline():
    disagree = report_of(aggregate(compared=1, mismatched=1, uncompared=1))
    agree = report_of(aggregate(compared=1, mismatched=0, uncompared=1))
    [first, second] = run_bun(METRIC, [disagree, agree])
    assert first["metric"]["total"] == 1
    assert first["metric"]["mismatches"] == 1
    assert first["metric"]["matched"] == 0
    assert first["metric"]["rate"] == 0
    assert first["metric"]["uncompared"] == 1
    assert second["metric"]["mismatches"] == 0
    assert second["metric"]["matched"] == 1
    assert second["metric"]["rate"] == 100
    assert second["metric"]["uncompared"] == 1


@needs_bun
def test_nway_summary_counts_matches_without_uncompared_pairs():
    disagree = report_of(aggregate(compared=1, mismatched=1, uncompared=1))
    agree = report_of(aggregate(compared=1, mismatched=0, uncompared=1))
    [first, second] = run_bun(METRIC, [disagree, agree])
    assert first["summary"]["overallMatchRate"] == 0
    assert first["summary"]["mismatchCount"] == 1
    assert first["summary"]["uncomparedCount"] == 1
    assert second["summary"]["overallMatchRate"] == 100
    assert second["summary"]["mismatchCount"] == 0


@needs_bun
def test_reports_without_the_field_read_as_before():
    legacy = aggregate(compared=10, mismatched=3, uncompared=0)
    legacy.pop("uncompared_mismatches")
    [result] = run_bun(METRIC, [report_of(legacy)])
    assert result["metric"]["mismatches"] == 3
    assert result["metric"]["matched"] == 7
    assert result["metric"]["uncompared"] == 0
    assert result["summary"]["overallMatchRate"] == 70


AGGREGATES = st.lists(
    st.tuples(st.integers(0, 50), st.integers(0, 50), st.integers(0, 50)).map(
        lambda t: (t[0], min(t[1], t[0]), t[2])
    ),
    min_size=1,
    max_size=4,
)


@needs_bun
@settings(max_examples=25, deadline=None, derandomize=True)
@given(batches=st.lists(AGGREGATES, min_size=1, max_size=4))
def test_property_headline_is_bounded_and_ignores_uncompared_pairs(batches):
    """Matched is never negative, the rate stays in [0, 100], and adding
    uncompared pairs to a report never changes its headline agreement."""
    reports, stripped = [], []
    for batch in batches:
        aggs = [
            aggregate(c, m, u, concept=f"{CONCEPT}{i}")
            for i, (c, m, u) in enumerate(batch)
        ]
        reports.append(report_of(*aggs))
        stripped.append(
            report_of(
                *(
                    aggregate(c, m, 0, concept=f"{CONCEPT}{i}")
                    for i, (c, m, _) in enumerate(batch)
                )
            )
        )
    results = run_bun(METRIC, reports + stripped)
    with_uncompared, without = results[: len(reports)], results[len(reports) :]
    for batch, got, want in zip(batches, with_uncompared, without):
        metric = got["metric"]
        assert 0 <= metric["matched"] <= metric["total"]
        assert metric["rate"] is None or 0 <= metric["rate"] <= 100
        assert metric["uncompared"] == sum(u for _, _, u in batch)
        for key in ("total", "mismatches", "matched", "rate"):
            assert metric[key] == want["metric"][key]
        assert got["summary"]["overallMatchRate"] == want["summary"]["overallMatchRate"]


# ── the household explorer ───────────────────────────────────────────────────
CASES = """
import { caseDisagreements, caseUncompared, caseUnexplainedCount }
  from "./dashboard/src/utils/caseMismatches.mjs";
const cases = await new Response(Bun.stdin.stream()).json();
console.log(JSON.stringify(cases.map((c) => ({
  disagreements: caseDisagreements(c).length,
  uncompared: caseUncompared(c).length,
  unexplained: caseUnexplainedCount(c),
}))));
"""


@needs_bun
def test_household_rows_mark_uncompared_pairs_and_do_not_count_them():
    cases = [
        {"id": "a", "m": [{"c": CONCEPT, "l": 1, "x": 2, "d": -1}, {"c": "b", "l": None, "x": 0, "u": True}]},
        {"id": "b", "m": [{"c": CONCEPT, "l": True, "x": True, "u": True}]},
        {"id": "c", "m": [{"c": CONCEPT, "l": 1, "x": 2, "d": -1, "e": "known"}]},
        {"id": "d"},
    ]
    assert run_bun(CASES, cases) == [
        {"disagreements": 1, "uncompared": 1, "unexplained": 1},
        {"disagreements": 0, "uncompared": 1, "unexplained": 0},
        {"disagreements": 1, "uncompared": 0, "unexplained": 0},
        {"disagreements": 0, "uncompared": 0, "unexplained": 0},
    ]


def test_household_explorer_reads_the_shared_helpers():
    source = (ROOT / "dashboard/src/components/Households.jsx").read_text()
    assert "caseMismatches.mjs" in source
    assert "not compared" in source
    # The explorer's own unexplained filter used to count every m row.
    assert "filter((m) => !m.e)" not in source


# ── Python readers ───────────────────────────────────────────────────────────
def us_report(uncompared: int):
    from axiom_oracles.bridges import us_populace

    return {
        "compared_values": 1,
        "mismatch_count": 1 + uncompared,
        "uncompared_mismatches": uncompared,
        "errors": [{"engine": "axiom"}] * uncompared,
        "output_summary": [
            {
                "surface": "s",
                "output": "o",
                "compared": 1,
                "mismatches": 1 + uncompared,
                "uncompared_mismatches": uncompared,
            }
        ],
    }, us_populace


def load_runner():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "uncompared_668_runner", ROOT / "scripts/run_comparison.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_comparison_summary_leaves_uncompared_pairs_out(tmp_path, capsys):
    data, _ = us_report(uncompared=1)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data))
    load_runner()._print_summary(path)
    out = capsys.readouterr().out
    assert "Mismatches:        1\n" in out
    assert "Uncompared:        1" in out
    assert "Agreement:         0.0000%" in out
    assert "0/1" in out and "-1/1" not in out


def test_run_comparison_case_summary_leaves_uncompared_pairs_out(tmp_path, capsys):
    data = {
        "case_count": 2,
        "cases": [],
        "aggregates": [aggregate(compared=1, mismatched=0, uncompared=1)],
    }
    data["aggregates"][0].pop("match_count")
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data))
    load_runner()._print_summary(path)
    out = capsys.readouterr().out
    assert "compared=1  matched=1" in out
    assert "uncompared=1" in out


def us_variable_report():
    from tests.test_native_snap_invalid_returns import us_compare

    return us_compare(None, 0.0)


def test_us_variable_text_summary_separates_uncompared_pairs(capsys):
    from axiom_oracles.bridges import us_populace

    report = us_variable_report()
    us_populace.print_report(
        report, tolerance=0.01, relative_tolerance=1e-9, max_differences=5
    )
    out = capsys.readouterr().out
    assert "Mismatches: 0\n" in out
    assert "Uncompared (engine errors): 1" in out
    assert "Errors: 1" in out
    assert "0/1 mismatch" in out


def test_fiit_text_summary_separates_uncompared_pairs(capsys):
    from axiom_oracles.bridges import tax_populace

    report = tax_populace.TaxComparisonReport(
        compared_tax_units=1,
        compared_persons=1,
        compared_values=1,
        mismatches=[
            tax_populace.TaxComparisonRow(
                surface="s", entity_id="tu_1", output="o",
                axiom=float("nan"), policyengine=0.0, diff=float("nan"),
            )
        ],
        output_summary=[
            {
                "surface": "s", "output": "o", "compared": 1, "mismatches": 1,
                "uncompared_mismatches": 1, "max_abs_diff": 0.0,
                "max_relative_diff": 0.0,
            }
        ],
        projection_notes=[],
        errors=[{"engine": "axiom"}],
    )
    tax_populace.print_report(report, tolerance=1, relative_tolerance=0)
    out = capsys.readouterr().out
    assert "Mismatches: 0\n" in out
    assert "Uncompared (engine errors): 1" in out
    assert "Errors: 1" in out
    assert "0/1 mismatch" in out


def workflow_summary_snippet() -> str:
    workflow = yaml.safe_load((ROOT / ".github/workflows/comparisons.yml").read_text())
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == "Summarize agreement":
                run = step["run"]
                start = run.index('python3 -c "') + len('python3 -c "')
                end = run.index('" >> "$GITHUB_STEP_SUMMARY"', start)
                return run[start:end]
    raise AssertionError("the comparisons workflow has no summary step")


def test_workflow_step_summary_leaves_uncompared_pairs_out(tmp_path):
    data, _ = us_report(uncompared=1)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data))
    snippet = workflow_summary_snippet().replace("$latest", str(path))
    out = subprocess.run(
        [sys.executable, "-c", snippet], capture_output=True, text=True, check=True
    ).stdout
    assert "agreement:       0.0000%" in out
    assert "uncompared:      1" in out


# ── the discrepancy ledger's patterns ────────────────────────────────────────
NODE = shutil.which("node")

CLASSES = r"""
const fs = require("fs");
eval(fs.readFileSync("dashboard/src/utils/caseMismatches.mjs", "utf8")
  .replaceAll("export function", "function"));
const ledger = fs.readFileSync("dashboard/src/components/OraclesV2.jsx", "utf8");
const begin = ledger.indexOf("function buildClasses(");
const end = ledger.indexOf("\nfunction ActionChip(", begin);
function topLevelAggregates(aggregates) { return aggregates || []; }
function suiteLabel(suite) { return suite; }
function suiteMeta() { return {}; }
function otherOracle() { return ""; }
function displayEngines() { return {}; }
function causeFor() { return null; }
eval(ledger.slice(begin, end));
const reports = JSON.parse(fs.readFileSync(0, "utf8"));
console.log(JSON.stringify(buildClasses(reports, []).map(
  (row) => [row.concept, row.kind, row.count])));
"""


@pytest.mark.skipif(NODE is None, reason="dashboard ledger requires node")
def test_discrepancy_patterns_leave_uncompared_rows_out():
    agg = aggregate(compared=1, mismatched=1, uncompared=1)
    report = report_of(agg)
    report["summary"] = {"mismatch_count": 2}
    report["mismatches"] = [
        {"concept": CONCEPT, "kind": "amount_difference", "difference": 5},
        {"concept": CONCEPT, "kind": "missing_left", "uncompared": True},
    ]
    only_uncompared = report_of(aggregate(compared=0, mismatched=0, uncompared=1, concept="x"))
    only_uncompared["summary"] = {"mismatch_count": 1}
    only_uncompared["mismatches"] = [{"concept": "x", "kind": "missing_right", "uncompared": True}]
    result = subprocess.run(
        [NODE, "-e", CLASSES], cwd=ROOT, input=json.dumps([report, only_uncompared]),
        capture_output=True, text=True, check=True, timeout=30,
    )
    assert json.loads(result.stdout) == [[CONCEPT, "amount_difference", 1]]


def test_program_page_patterns_mirror_the_ledger():
    """ProgramPage's WhySection repeats buildClasses' counting inline."""
    source = (ROOT / "dashboard/src/components/ProgramPage.jsx").read_text()
    assert "if (m?.uncompared === true) continue;" in source
    assert "+ comparedMismatchCount(agg)," in source
    assert "agg.mismatch_count" not in source
