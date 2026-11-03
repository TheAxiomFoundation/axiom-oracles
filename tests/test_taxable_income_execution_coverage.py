"""The taxable-income suite requires real, same-case final-output evidence."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from functools import cache
import json
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.conformance.loader import parse as parse_universe
from axiom_oracles.conformance.scoreboard import score_jurisdiction


ROOT = Path(__file__).parents[1]
SUITE = "us-taxable-income-grid"
POLICY_ID = "us-pe:taxable_income"
CONCEPT = "us:policies/income_tax/taxable_income_pipeline#federal_taxable_income"
PROPERTY_SETTINGS = settings(max_examples=50, deadline=None, derandomize=True)


@cache
def _suite_evidence():
    universe = parse_universe(ROOT / "conformance/us-pe.yaml")
    policy = next(policy for policy in universe.policies if policy.id == POLICY_ID)
    assert policy.in_scope is True
    assert policy.suite == SUITE
    report = json.loads(
        (ROOT / "dashboard/public/data/axiom-policyengine-us-taxable-income-grid.json")
        .read_text()
    )
    return replace(universe, policies=[policy]), report


@PROPERTY_SETTINGS
@given(
    engine=st.sampled_from(("axiom", "policyengine")),
    invalid_value=st.sampled_from((None, float("nan"), float("inf"), "missing")),
)
def test_taxable_income_coverage_requires_both_engines_return_a_numeric_final_output(
    engine, invalid_value,
):
    """A report's counts and output labels cannot replace either returned value."""
    universe, original = _suite_evidence()
    report = deepcopy(original)
    report.pop("attestation", None)
    report["observed_outputs"] = [
        row for row in report.get("observed_outputs", [])
        if row.get("engine") != engine
    ]
    for case in report["cases"]:
        case[engine] = invalid_value
        components = case.get(f"{engine}_components")
        if isinstance(components, dict):
            for output in ("taxable_income", CONCEPT):
                if output in components:
                    components[output] = invalid_value

    board, rows = score_jurisdiction(universe, [report])
    assert board.policies_in_scope == 1
    assert board.covered == 0
    assert rows[0].in_scope is True
    assert rows[0].suite == SUITE
    assert rows[0].covered is False
    assert board.conformant is False


@PROPERTY_SETTINGS
@given(errors=st.integers(min_value=1, max_value=100))
def test_taxable_income_run_errors_never_count_as_coverage(errors):
    """Every positive execution-error count preserves the in-scope coverage gap."""
    universe, original = _suite_evidence()
    report = deepcopy(original)
    report.pop("attestation", None)
    report["summary"]["error_count"] = errors

    board, rows = score_jurisdiction(universe, [report])
    assert board.policies_in_scope == 1
    assert board.covered == 0
    assert rows[0].covered is False
    assert board.conformant is False


def test_public_taxable_income_detail_publishes_the_same_attested_execution():
    """Canonical and served detail expose the final output that earns coverage."""
    universe, report = _suite_evidence()
    board, rows = score_jurisdiction(universe, [report])
    assert board.covered == 1
    expected = asdict(rows[0])
    assert expected.get("output_attestation") == "attested"
    assert expected.get("attested_outputs") == ["taxable_income"]
    for path in (
        ROOT / "conformance/detail/us-pe.json",
        ROOT / "dashboard/public/data/conformance_detail_us-pe.json",
    ):
        document = json.loads(path.read_text())
        row = next(row for row in document["policies"] if row["id"] == POLICY_ID)
        assert row == expected
