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
