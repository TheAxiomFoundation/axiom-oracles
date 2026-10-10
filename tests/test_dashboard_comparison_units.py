"""Mixed comparison units count once per case, independently of concept checks.

The dashboard's historical ``households`` helper/property names remain for
compatibility; their values include parameter cases and federal tax units.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
BUN = shutil.which("bun")
pytestmark = pytest.mark.skipif(BUN is None, reason="dashboard helpers require Bun")

# The expected oracle and case unit come from the generated inputs, rather
# than asking the production helpers how they classify or count each report.
SOURCES = (
    ("ssa-parameters", "policyengine", "policyengine", "parameter"),
    ("fiit-taxsim-ecps", "taxsim", "taxsim", "tax_unit"),
    ("al-snap-ecps", "policyengine", "policyengine", "household"),
    ("uk-worker-pit", "euromod", "ukmod", "household"),
    ("be-worker-pit", "euromod", "euromod", "household"),
    ("gh-paye", "euromod", "southmod", "household"),
)

RUN_HELPERS = """
import { groupByOracle, reportHouseholds, verificationReports }
  from "./dashboard/src/utils/roster.js";
const batches = await new Response(Bun.stdin.stream()).json();
const results = batches.map(({reports, hidden}) => {
  const included = verificationReports(reports, new Set(hidden));
  const roster = groupByOracle(included);
  return {
    perReport: reports.map(reportHouseholds),
    included: included.map(r => r.id),
    groups: Object.fromEntries(roster.map(o => [o.id, {
      cases: o.households,
      reports: o.reports.map(r => r.id),
    }])),
    total: roster.reduce((n, o) => n + o.households, 0),
  };
});
console.log(JSON.stringify(results));
"""


@st.composite
def mixed_reports(draw):
    sources = list(SOURCES[:3]) + draw(
        st.lists(st.sampled_from(SOURCES), max_size=5)
    )
    hidden = draw(st.sets(st.sampled_from([source[2] for source in SOURCES])))
    reports = []
    expected_counts = {}
    expected_groups = defaultdict(lambda: {"cases": 0, "reports": []})
    for index, (suite, engine, oracle, unit) in enumerate(sources):
        count = draw(st.integers(min_value=0, max_value=30))
        explicit_count = draw(st.booleans())
        materialized_count = (
            draw(st.integers(min_value=0, max_value=count))
            if explicit_count
            else count
        )
        # Scalar parameter cases have no household entities to count.
        cases = (
            list(range(materialized_count))
            if unit == "parameter"
            else [{"id": f"case-{i}", "unit": unit} for i in range(materialized_count)]
        )
        axiom_on_left = draw(st.booleans())
        engines = (
            {"left": "axiom", "right": engine}
            if axiom_on_left
            else {"left": engine, "right": "axiom"}
        )
        # Keep all three case units in the candidate roster. Additional
        # reports can be diagnostics, cross-checks, or missing aggregates.
        disposition = (
            "measured"
            if index < 3
            else draw(st.sampled_from(["measured", "diagnostic", "cross", "empty"]))
        )
        if disposition == "diagnostic":
            suite = "nyc-income-tax-ecps-diagnostic"
        elif disposition == "cross":
            engines = {"left": "policyengine", "right": "taxsim"}
        checks = draw(st.integers(min_value=0, max_value=300))
        aggregates = [{"concept": "liability", "comparison_count": checks}]
        aggregates.extend(
            {"concept": f"component-{i}", "parent": "liability", "comparison_count": n}
            for i, n in enumerate(
                draw(st.lists(st.integers(min_value=0, max_value=300), max_size=5))
            )
        )
        if disposition == "empty":
            aggregates = []
        report = {
            "id": f"report-{index}",
            "suite": suite,
            "engines": engines,
            "cases": cases,
            "aggregates": aggregates,
            "metadata": {"case_unit": unit},
        }
        if explicit_count:
            report["case_count"] = count
        elif draw(st.booleans()):
            report["case_count"] = None
        reports.append(report)
        expected_counts[report["id"]] = count
        if disposition == "measured" and oracle not in hidden:
            expected_groups[oracle]["cases"] += count
            expected_groups[oracle]["reports"].append(report["id"])

    permutation = draw(st.permutations(range(len(reports))))
    reports = [reports[index] for index in permutation]
    return reports, sorted(hidden), expected_counts, dict(expected_groups)


def _assert_mixed_counts(reports, hidden, counts, expected_groups):
    altered = copy.deepcopy(list(reversed(reports)))
    for report in altered:
        if report["aggregates"]:
            # Extra independent checks change check totals, while case counts
            # must stay fixed. Metadata does not turn scalars into households.
            report["aggregates"].append(
                {"concept": "extra-concept", "comparison_count": 999}
            )
        report["metadata"]["households"] = 999
    batches = [
        {"reports": reports, "hidden": hidden},
        {"reports": altered, "hidden": hidden},
    ]
    result = subprocess.run(
        [BUN, "-e", RUN_HELPERS],
        cwd=ROOT,
        input=json.dumps(batches),
        capture_output=True,
        text=True,
        check=True,
    )
    for batch, actual in zip(batches, json.loads(result.stdout), strict=True):
        assert actual["perReport"] == [counts[r["id"]] for r in batch["reports"]]
        expected_ids = sorted(
            report_id
            for group in expected_groups.values()
            for report_id in group["reports"]
        )
        assert sorted(actual["included"]) == expected_ids
        assert set(actual["groups"]) == set(expected_groups)
        for oracle, expected in expected_groups.items():
            group = actual["groups"][oracle]
            assert group["cases"] == expected["cases"]
            assert sorted(group["reports"]) == sorted(expected["reports"])
        assert actual["total"] == sum(group["cases"] for group in expected_groups.values())


@settings(max_examples=100, deadline=None, database=None)
@given(mixed_reports())
def test_mixed_units_count_once_regardless_of_concepts_and_report_order(inputs):
    _assert_mixed_counts(*inputs)
