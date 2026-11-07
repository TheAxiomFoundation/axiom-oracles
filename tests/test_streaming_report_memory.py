"""A streamed comparison report holds observation rows on disk, not in memory.

With ``case_rows_path`` the accumulator spools every returned-output row,
as it spools case rows, so its retained memory does not grow with the
returned values. Its serialized report and its stamp counts stay byte for
byte those of the in-memory accumulator.
"""

from __future__ import annotations

import gc
import json
import tracemalloc

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import ComparisonReportAccumulator
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult

TARGETS = [f"component_{index}" for index in range(8)]
MAPPINGS = [
    ProgramMapping(
        standard="us:test#tax",
        description="Tax",
        category="tax",
        comparison="amount",
        tolerance=1,
        targets={"axiom": list(TARGETS), "policyengine": list(TARGETS)},
    ),
    ProgramMapping(
        standard="us:test#eligible",
        description="Eligible",
        category="benefits",
        comparison="eligibility",
        targets={"axiom": "eligible", "policyengine": "is_eligible"},
    ),
]


def _accumulator(path=None, *, include_inputs=False):
    return ComparisonReportAccumulator(
        suite_name="memory-probe",
        population="synthetic",
        locales={"US"},
        scope=None,
        mappings=MAPPINGS,
        case_rows_path=path,
        include_inputs=include_inputs,
    )


def _batch(start, size, values=None):
    """One batch whose engines agree, so no mismatch rows are retained."""
    cases, left, right = [], [], []
    for case_id in range(start, start + size):
        returned = (
            values[case_id - start] if values is not None
            else {name: float(case_id % 97) + 0.25 for name in TARGETS}
        )
        cases.append(Case(case_id=case_id, period="2026"))
        left.append(EngineResult("axiom", case_id, {**returned, "eligible": True}))
        right.append(EngineResult("policyengine", case_id, {**returned, "is_eligible": True}))
    return cases, Comparator(MAPPINGS).compare(left, right)


def _retained_bytes(accumulator, case_count, batch_size=50):
    """Bytes the accumulator still holds after ``case_count`` cases."""
    gc.collect()
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        for start in range(0, case_count, batch_size):
            accumulator.add_batch(*_batch(start, batch_size))
        gc.collect()
        return tracemalloc.get_traced_memory()[0] - before
    finally:
        tracemalloc.stop()


def test_streamed_observation_memory_does_not_scale_with_case_count(tmp_path):
    """Each case returns 18 values; a streamed accumulator keeps none of them.

    The bound allows the per-case identity set the accumulator needs to
    refuse repeated case ids, and nothing per returned value. Before the
    spool, every returned value stayed in memory: roughly 3 KB per case.
    """
    small = _retained_bytes(_accumulator(tmp_path / "small" / "cases.jsonl"), 50)
    large = _retained_bytes(_accumulator(tmp_path / "large" / "cases.jsonl"), 250)
    per_case = (large - small) / 200
    assert per_case < 300, f"{per_case:.0f} bytes retained per extra case"


def _write(accumulator, path, batches):
    for cases, comparisons in batches:
        accumulator.add_batch(cases, comparisons)
    accumulator.write_json(path)
    return path.read_bytes()


VALUES = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(-10**18, 10**18),
    st.floats(allow_nan=False, allow_infinity=False, width=64),
)


@settings(
    max_examples=25, deadline=None, derandomize=True,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    returned=st.lists(
        st.fixed_dictionaries({name: VALUES for name in TARGETS}), min_size=1, max_size=12,
    ),
    batch_size=st.integers(1, 5),
    include_inputs=st.booleans(),
)
def test_property_streamed_report_is_byte_identical_to_in_memory(
    tmp_path_factory, returned, batch_size, include_inputs
):
    """Same evidence, same stamp counts, same bytes, however the run is batched."""
    directory = tmp_path_factory.mktemp("report")
    batches = [
        _batch(start, len(chunk), chunk)
        for start in range(0, len(returned), batch_size)
        for chunk in [returned[start:start + batch_size]]
    ]
    in_memory = _accumulator(include_inputs=include_inputs)
    streamed = _accumulator(directory / "rows" / "cases.jsonl", include_inputs=include_inputs)
    expected = _write(in_memory, directory / "memory.json", batches)
    actual = _write(streamed, directory / "streamed.json", batches)
    assert actual == expected
    report = json.loads(actual)
    assert report["attestation"] == in_memory.to_dict()["attestation"]
    assert streamed.to_dict() == json.loads(json.dumps(in_memory.to_dict()))
    assert len(report["observed_outputs"]) == sum(
        2 * len(TARGETS) + 2 for _ in returned
    )


def test_empty_report_streams_identically(tmp_path):
    expected = _write(_accumulator(), tmp_path / "memory.json", [])
    actual = _write(_accumulator(tmp_path / "rows" / "cases.jsonl"), tmp_path / "streamed.json", [])
    assert actual == expected
    assert json.loads(actual)["observed_outputs"] == []


def _cli_peak(monkeypatch, tmp_path, case_count, batch_size=25):
    """Peak bytes allocated by ``compare --output``, end to end, with stub engines."""
    import importlib

    from click.testing import CliRunner

    cli_module = importlib.import_module("axiom_oracles.cli")
    cases = [Case(case_id=index, period="2026") for index in range(case_count)]
    monkeypatch.setattr(cli_module, "_load_population_cases", lambda **kwargs: cases)
    monkeypatch.setattr(cli_module, "_echo_resolved_axiom_composition", lambda *args: None)
    monkeypatch.setattr(cli_module, "comparable_mappings", lambda *args, **kwargs: MAPPINGS)
    monkeypatch.setattr(
        cli_module, "_prepare_cases_for_engines", lambda batch, *args, **kwargs: batch
    )

    class Runner:
        def __init__(self, engine):
            self.engine = engine
            self.flag = "eligible" if engine == "axiom" else "is_eligible"

        def run_cases(self, batch, variables):
            return [
                EngineResult(self.engine, case.case_id, {
                    **{name: float(case.case_id % 97) + 0.25 for name in TARGETS},
                    self.flag: True,
                })
                for case in batch
            ]

    monkeypatch.setattr(
        cli_module, "_build_runner", lambda engine, *args, **kwargs: Runner(engine)
    )
    output = tmp_path / f"report-{case_count}.json"
    runner = CliRunner()
    gc.collect()
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        run = runner.invoke(cli_module.cli, [
            "compare", "axiom", "policyengine", "--output", str(output),
            "--comparison-batch-size", str(batch_size),
        ])
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert run.exit_code == 0, run.output
    assert json.loads(output.read_text())["case_count"] == case_count
    return peak


def test_cli_compare_output_peak_does_not_scale_with_returned_values(monkeypatch, tmp_path):
    """The whole ``compare --output`` run, not only add_batch, stays bounded.

    The population's Case objects are inherently held for the run; the bound
    allows them and nothing per returned value. Reading the spool back for
    the summary echo cost roughly 11 KB per case.
    """
    _cli_peak(monkeypatch, tmp_path, 10)  # imports and first-run caches
    small = _cli_peak(monkeypatch, tmp_path, 100)
    large = _cli_peak(monkeypatch, tmp_path, 400)
    per_case = (large - small) / 300
    assert per_case < 1_500, f"{per_case:.0f} peak bytes per extra case"


def test_observed_outputs_bytes_match_the_whole_list_encoding(tmp_path):
    """The streamed entry is exactly ``_top_level_json_entry`` of the whole list.

    This pins the writer against the encoder it replaces, rather than
    against itself.
    """
    from axiom_oracles.comparison.report import _top_level_json_entry

    for count, name in ((3, "some"), (0, "none")):
        accumulator = _accumulator(tmp_path / name / "cases.jsonl")
        if count:
            accumulator.add_batch(*_batch(0, count))
        path = tmp_path / f"{name}.json"
        accumulator.write_json(path)
        text = path.read_text()
        rows = accumulator.to_dict()["observed_outputs"]
        assert len(rows) == count * (2 * len(TARGETS) + 2)
        assert _top_level_json_entry("observed_outputs", rows) + ",\n" in text
