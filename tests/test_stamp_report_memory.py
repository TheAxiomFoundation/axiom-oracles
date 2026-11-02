"""Provenance stamping holds one parse of a report and writes the same bytes.

``_stamp_report_provenance`` used to keep the report's whole text, parse it
twice, and build a whole re-serialized string for each candidate format it
tried and again to write. A multi-GB report held several copies at once
(#630). It now parses once, compares each candidate format by streaming its
encoding against the file, and streams the result back. The written bytes
are those of the original text-based implementation, kept here as the
reference for the differential.
"""

from __future__ import annotations

import gc
import importlib.util
import json
import tracemalloc
from functools import lru_cache
from pathlib import Path

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).parents[1]


@lru_cache(maxsize=1)
def _run_comparison():
    spec = importlib.util.spec_from_file_location(
        "stamp_memory_run_comparison", ROOT / "scripts" / "run_comparison.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reference_stamp(
    output, provenance, *, require_engine_versions=False, preserve_runner_provenance=False
):
    """The text-based implementation this change replaces, verbatim but for
    the edit step, which both implementations share."""
    rc = _run_comparison()
    try:
        original_text = output.read_text()
        data = json.loads(original_text)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    rc._apply_report_provenance(
        data,
        provenance,
        require_engine_versions=require_engine_versions,
        preserve_runner_provenance=preserve_runner_provenance,
    )
    trailing = "\n" if original_text.endswith("\n") else ""
    for sort_keys in (True, False):
        for indent in (2, 1):
            reserialized = json.dumps(
                json.loads(original_text), indent=indent, sort_keys=sort_keys
            )
            if original_text in (reserialized, reserialized + "\n"):
                output.write_text(
                    json.dumps(data, indent=indent, sort_keys=sort_keys) + trailing
                )
                return
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + trailing)


def _outcome(stamp, path, provenance, flags):
    try:
        stamp(path, provenance, **flags)
    except SystemExit as exc:
        return ("refused", str(exc), path.read_bytes())
    return ("written", None, path.read_bytes())


def _both(tmp_path, text, provenance, **flags):
    reference, candidate = tmp_path / "reference.json", tmp_path / "candidate.json"
    for path in (reference, candidate):
        path.write_text(text)
    expected = _outcome(_reference_stamp, reference, provenance, flags)
    actual = _outcome(_run_comparison()._stamp_report_provenance, candidate, provenance, flags)
    return expected, actual


# --- differential -----------------------------------------------------------

SCALARS = st.one_of(
    st.none(), st.booleans(), st.integers(-10**20, 10**20),
    st.floats(allow_nan=True, allow_infinity=True), st.text(max_size=8),
)
JSON = st.recursive(
    SCALARS,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=6), children, max_size=4),
    ),
    max_leaves=25,
)
FORMATS = st.sampled_from([
    {"indent": 2, "sort_keys": True}, {"indent": 1, "sort_keys": True},
    {"indent": 2, "sort_keys": False}, {"indent": 1, "sort_keys": False},
    {"indent": None, "sort_keys": False}, {"indent": 4, "sort_keys": True},
    {"indent": 2, "sort_keys": False, "separators": (", ", ": ")},
])
PIN = {"policyengine_package": "policyengine==4.18.9", "policyengine_us": "1.767.3",
       "policyengine_core": "3.30.3"}
PROVENANCE = st.fixed_dictionaries(
    {"schema": st.just("axiom_oracles.provenance.v1"),
     "generated_by": st.sampled_from(["scripts/run_comparison.py::probe", None])},
    optional={
        "engine": st.fixed_dictionaries({}, optional={
            "version": st.just("0.4.0"), "axiom_rules_engine_version": st.just("0.3.0"),
        }),
        "oracle": st.just(PIN),
        "reemitted_report": st.booleans(),
        "rulespecs": st.just([{"repo": "o/r", "sha": "a" * 40, "dirty": False}]),
        "tuple_value": st.just(("a", 1)),
    },
)
ENGINES = st.one_of(
    st.none(),
    st.just({"left": "axiom", "right": "policyengine"}),
    st.just({"left": "axiom", "right": "policyengine", "versions": {
        "policyengine": "4.18.9", "policyengine_core": "3.30.3", "policyengine_us": "1.767.3",
    }}),
    st.just({"left": "axiom", "versions": {"policyengine": "4.0.0"}}),
)
EXISTING = st.one_of(
    st.none(),
    st.just({"engine": {"commit": "b" * 40}, "producer": "de"}),
    st.just({"relation_binding_diagnostics": {"count": 1, "by_relation": {}}}),
)


@settings(
    max_examples=150, deadline=None, derandomize=True,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(
    body=st.dictionaries(st.text(max_size=6), JSON, max_size=6),
    engines=ENGINES,
    existing=EXISTING,
    fmt=FORMATS,
    trailing=st.sampled_from(["", "\n", "\n\n", " "]),
    provenance=PROVENANCE,
    require_engine_versions=st.booleans(),
    preserve_runner_provenance=st.booleans(),
)
@example(body={}, engines=None, existing=None, fmt={"indent": 2, "sort_keys": True},
         trailing="\n", provenance={"schema": "v1", "generated_by": None},
         require_engine_versions=True, preserve_runner_provenance=False)
def test_property_stamp_bytes_equal_the_text_implementation(
    tmp_path_factory, body, engines, existing, fmt, trailing, provenance,
    require_engine_versions, preserve_runner_provenance,
):
    report = dict(body)
    if engines is not None:
        report["engines"] = engines
    if existing is not None:
        report["provenance"] = existing
    text = json.dumps(report, **fmt) + trailing
    expected, actual = _both(
        tmp_path_factory.mktemp("stamp"), text, provenance,
        require_engine_versions=require_engine_versions,
        preserve_runner_provenance=preserve_runner_provenance,
    )
    assert actual == expected


@pytest.mark.parametrize("text", [
    "", "not json", "[1, 2]", '"report"', "null", "{", '{"a": 1}{"b": 2}',
    '{"a": 1, "a": 2}', '{\n  "b": 1,\n  "a": 2\n}\r\n', '{"a": NaN}\n',
])
def test_unusual_files_match_the_text_implementation(tmp_path, text):
    expected, actual = _both(tmp_path, text, {"schema": "v1"})
    assert actual == expected


def test_committed_reports_stamp_identically(tmp_path):
    """Finished reports of every committed format stamp to the same bytes."""
    provenance = {"schema": "axiom_oracles.provenance.v1", "generated_by": "probe",
                  "engine": {"version": "0.4.0"}, "oracle": PIN}
    checked = 0
    for source in sorted((ROOT / "reports").glob("*.json"))[:12]:
        if source.stat().st_size > 8_000_000:
            continue
        expected, actual = _both(tmp_path, source.read_text(), provenance)
        assert actual == expected, source.name
        checked += 1
    assert checked >= 5


# --- memory -----------------------------------------------------------------


def _big_report(path: Path, *, indent: int, sort_keys: bool, cases: int = 1_500) -> None:
    report = {
        "suite": "memory-probe",
        "engines": {"left": "axiom", "right": "policyengine", "versions": {
            "policyengine": "4.18.9", "policyengine_core": "3.30.3",
            "policyengine_us": "1.767.3",
        }},
        "provenance": {"generated_by": "old"},
        "cases": [
            {
                "case_id": f"case-{index}",
                "metadata": {"inputs": [{"name": f"input_{k}", "value": index * k + 0.5}
                                        for k in range(12)]},
                "matches": [{"concept": f"us:test#c{k}", "left": k + 0.25, "right": k + 0.25}
                            for k in range(6)],
                "mismatches": [],
            }
            for index in range(cases)
        ],
    }
    path.write_text(json.dumps(report, indent=indent, sort_keys=sort_keys) + "\n")


def _peak(function) -> int:
    gc.collect()
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        function()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


@pytest.mark.parametrize(("indent", "sort_keys"), [(2, True), (1, True), (2, False), (1, False)])
def test_stamp_peak_memory_is_one_parse(tmp_path, indent, sort_keys):
    """Peak allocation while stamping stays within one parse of the report.

    The baseline is ``json.load`` of the same file: its text plus one parsed
    object. The text implementation peaked at more than twice that, holding
    the text, two parses and a whole re-serialized string at once.
    """
    path = tmp_path / "report.json"
    _big_report(path, indent=indent, sort_keys=sort_keys)
    original = path.read_bytes()

    def load():
        with open(path) as handle:
            json.load(handle)

    baseline = _peak(load)
    provenance = {"schema": "axiom_oracles.provenance.v1", "oracle": PIN,
                  "engine": {"version": "0.4.0"}}
    stamped = _peak(lambda: _run_comparison()._stamp_report_provenance(
        path, provenance, require_engine_versions=True,
    ))
    assert stamped <= 1.2 * baseline, (
        f"stamping peaked at {stamped / baseline:.2f}x one parse"
    )
    # The stamp still kept the format: only the provenance and versions moved.
    written = json.loads(path.read_text())
    assert written["provenance"] == provenance
    assert written["engines"]["versions"]["axiom_rules_engine"] == "0.4.0"
    path.write_bytes(original)
    reference = tmp_path / "reference.json"
    reference.write_bytes(original)
    _reference_stamp(reference, provenance, require_engine_versions=True)
    _run_comparison()._stamp_report_provenance(path, provenance, require_engine_versions=True)
    assert path.read_bytes() == reference.read_bytes()
