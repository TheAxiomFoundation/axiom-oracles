from dataclasses import replace

import pytest
from click.testing import CliRunner

from axiom_oracles.cli import _filter_comparisons_for_case_outputs
from axiom_oracles.comparison.comparator import Comparator, HouseholdComparison
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import (
    ComparisonReportAccumulator,
    build_comparison_report,
)
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


MAPPING = ProgramMapping(
    standard="test:amount",
    description="Fixture amount",
    category="fixture",
    comparison="amount",
    targets={"axiom": "amount", "policyengine": "amount"},
)


def result(side, case_id, values=None):
    return EngineResult(side, case_id, {"amount": 10} if values is None else values)


def comparison(case_id):
    return Comparator([MAPPING]).compare(
        [result("axiom", case_id)], [result("policyengine", case_id)]
    )[0]


def accumulator(**kwargs):
    return ComparisonReportAccumulator(
        suite_name="completeness",
        population="fixture",
        locales=set(),
        scope=None,
        mappings=[MAPPING],
        **kwargs,
    )


@pytest.mark.parametrize(
    "left_ids,right_ids,reason",
    [
        ([1, 1], [1], "Duplicate left"),
        ([1], [1, 1], "Duplicate right"),
        ([1, 2], [1], "missing \\[2\\]"),
        ([1], [1, 2], "unexpected \\[2\\]"),
        ([1], [], "missing \\[1\\]"),
        ([], [1], "unexpected \\[1\\]"),
        ([1, 2], [3, 4], "Invalid right"),
    ],
)
def test_result_ids_must_form_a_bijection(left_ids, right_ids, reason):
    with pytest.raises(ValueError, match=reason):
        Comparator([MAPPING]).compare(
            [result("axiom", key) for key in left_ids],
            [result("policyengine", key) for key in right_ids],
        )


def test_result_order_is_irrelevant_but_ids_are_not_coerced():
    rows = Comparator([MAPPING]).compare(
        [result("axiom", 1), result("axiom", "1")],
        [result("policyengine", "1"), result("policyengine", 1)],
    )
    assert [row.household_id for row in rows] == [1, "1"]
    assert all(row.match_rate == 100 for row in rows)


def test_both_missing_outputs_remain_in_the_report_denominator():
    other = replace(
        MAPPING,
        standard="test:other",
        targets={"axiom": "other", "policyengine": "other"},
    )
    rows = Comparator([MAPPING, other]).compare(
        [result("axiom", 1)], [result("policyengine", 1)]
    )
    report = build_comparison_report(
        suite_name="completeness",
        population="fixture",
        locales=set(),
        scope=None,
        cases=[Case(case_id=1, period="2026")],
        mappings=[MAPPING, other],
        comparisons=rows,
    )
    assert rows[0].match_rate == 50
    assert report["case_count"] == 1
    assert report["summary"]["comparison_count"] == 2
    assert report["summary"]["match_count"] == 1
    assert report["summary"]["mismatch_count"] == 1
    assert report["mismatches"][0]["kind"] == "missing_both"


@pytest.mark.parametrize("values", [{"a": 10}, {"a": 10, "b": None}, {}])
def test_sum_mapping_requires_every_component(values):
    mapping = replace(MAPPING, targets={"axiom": ["a", "b"], "policyengine": "amount"})
    [row] = Comparator([mapping]).compare(
        [result("axiom", 1, values)], [result("policyengine", 1)]
    )
    assert row.comparisons[0].left_value is None
    assert row.mismatch_count == 1


def test_zero_sum_components_are_present_values():
    mapping = replace(MAPPING, targets={"axiom": ["a", "b"], "policyengine": "amount"})
    [row] = Comparator([mapping]).compare(
        [result("axiom", 1, {"a": 10, "b": 0})], [result("policyengine", 1)]
    )
    assert row.match_rate == 100


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_missing_sum_component_does_not_hide_another_non_finite_component(value):
    mapping = replace(
        MAPPING, targets={"axiom": ["a", "b"], "policyengine": "amount"}
    )
    with pytest.raises(ValueError, match="Non-finite component 'a'"):
        Comparator([mapping]).compare(
            [result("axiom", 1, {"a": value})], [result("policyengine", 1)]
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("kind", ["amount", "eligibility"])
@pytest.mark.parametrize("side", ["left", "right"])
def test_non_finite_values_are_explicit_errors(value, kind, side):
    values = {"amount": value}
    left = result("axiom", 1, values if side == "left" else {})
    right = result("policyengine", 1, values if side == "right" else {})
    with pytest.raises(ValueError, match="Non-finite"):
        Comparator([replace(MAPPING, comparison=kind)]).compare([left], [right])


def test_empty_comparison_is_not_perfect_agreement():
    assert HouseholdComparison(1, "axiom", "policyengine").match_rate == 0
    with pytest.raises(ValueError, match="No comparable mappings"):
        Comparator([]).compare([result("axiom", 1)], [result("policyengine", 1)])


def test_duplicate_mapping_concepts_are_rejected():
    with pytest.raises(ValueError, match="Duplicate mapping concepts"):
        Comparator([MAPPING, MAPPING])


def test_finite_inputs_with_an_overflowing_difference_are_rejected():
    with pytest.raises(ValueError, match="Non-finite difference"):
        Comparator([MAPPING]).compare(
            [result("axiom", 1, {"amount": 1e308})],
            [result("policyengine", 1, {"amount": -1e308})],
        )


@pytest.mark.parametrize(
    "case_ids,comparison_ids,reason",
    [
        ([1, 2], [1], "missing \\[2\\]"),  # both engines dropped a submitted case
        ([1], [1, 2], "unexpected \\[2\\]"),
        ([1, 1], [1], "Duplicate submitted"),
        ([1], [1, 1], "Duplicate comparison"),
    ],
)
def test_report_rejects_incomplete_or_duplicate_batches_without_mutation(
    case_ids, comparison_ids, reason, tmp_path
):
    path = tmp_path / "cases.jsonl"
    acc = accumulator(case_rows_path=path)
    before = acc.to_dict()
    with pytest.raises(ValueError, match=reason):
        acc.add_batch(
            [Case(case_id=key, period="2026") for key in case_ids],
            [comparison(key) for key in comparison_ids],
        )
    assert acc.to_dict() == before
    assert path.read_text() == ""


def test_streaming_report_rejects_repeated_ids_across_batches(tmp_path):
    path = tmp_path / "cases.jsonl"
    acc = accumulator(case_rows_path=path)
    cases, rows = [Case(case_id=1, period="2026")], [comparison(1)]
    acc.add_batch(cases, rows)
    before, stored = acc.to_dict(), path.read_text()
    with pytest.raises(ValueError, match="repeated across batches"):
        acc.add_batch(cases, rows)
    assert acc.to_dict() == before
    assert path.read_text() == stored


def test_streaming_report_rejects_an_engine_pair_change_without_mutation():
    acc = accumulator()
    acc.add_batch([Case(case_id=1, period="2026")], [comparison(1)])
    before = acc.to_dict()
    with pytest.raises(ValueError, match="engine pair changed"):
        acc.add_batch(
            [Case(case_id=2, period="2026")],
            [replace(comparison(2), right_engine="different-oracle")],
        )
    assert acc.to_dict() == before


@pytest.mark.parametrize("defect", ["missing", "extra", "duplicate", "empty"])
def test_report_requires_every_requested_output_exactly_once(defect):
    row = comparison(1)
    cases = [Case(case_id=1, period="2026", outputs=("test:amount",))]
    if defect == "missing":
        cases = [replace(cases[0], outputs=("test:amount", "test:other"))]
    elif defect == "extra":
        row = replace(
            row,
            comparisons=[
                *row.comparisons,
                replace(row.comparisons[0], variable="extra"),
            ],
        )
    elif defect == "duplicate":
        row = replace(row, comparisons=row.comparisons * 2)
    else:
        row = replace(row, comparisons=[])
    with pytest.raises(ValueError):
        accumulator().add_batch(cases, [row])


def test_case_specific_requested_outputs_preserve_their_explicit_scope():
    other = replace(
        MAPPING,
        standard="test:other",
        targets={"axiom": "other", "policyengine": "other"},
    )
    cases = [
        Case(case_id=1, period="2026", outputs=("test:amount",)),
        Case(case_id=2, period="2026", outputs=("test:other",)),
    ]
    rows = Comparator([MAPPING, other]).compare(
        [result("axiom", 1), result("axiom", 2, {"other": 20})],
        [result("policyengine", 1), result("policyengine", 2, {"other": 20})],
    )
    report = build_comparison_report(
        suite_name="scoped",
        population="fixture",
        locales=set(),
        scope=None,
        cases=cases,
        mappings=[MAPPING, other],
        comparisons=_filter_comparisons_for_case_outputs(cases, rows),
    )
    assert report["case_count"] == 2
    assert report["summary"]["comparison_count"] == 2
    assert report["summary"]["match_count"] == 2


def test_cli_fails_cleanly_without_writing_a_partial_report(monkeypatch, tmp_path):
    import importlib

    cli_module = importlib.import_module("axiom_oracles.cli")
    cases = [Case(case_id=1, period="2026"), Case(case_id=2, period="2026")]
    monkeypatch.setattr(cli_module, "_load_population_cases", lambda **kwargs: cases)
    monkeypatch.setattr(
        cli_module, "_echo_resolved_axiom_composition", lambda *args: None
    )
    monkeypatch.setattr(
        cli_module, "comparable_mappings", lambda *args, **kwargs: [MAPPING]
    )
    monkeypatch.setattr(
        cli_module, "_prepare_cases_for_engines", lambda batch, *args, **kwargs: batch
    )

    class Runner:
        def __init__(self, engine):
            self.engine = engine

        def run_cases(self, batch, variables):
            ids = [1, 2] if self.engine == "axiom" else [1]
            return [result(self.engine, key) for key in ids]

    monkeypatch.setattr(
        cli_module, "_build_runner", lambda engine, *args, **kwargs: Runner(engine)
    )
    output = tmp_path / "report.json"
    run = CliRunner().invoke(
        cli_module.cli,
        [
            "compare",
            "axiom",
            "policyengine",
            "--output",
            str(output),
        ],
    )
    assert run.exit_code == 1, run.output
    assert "Invalid comparison results" in run.output
    assert "missing [2]" in run.output
    assert not output.exists()
