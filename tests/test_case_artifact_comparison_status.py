"""Served and preserved case artifacts retain the native comparison verdict."""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings, strategies as st

from tests.test_emit_case_artifacts import _load_module, _write_fixture
from tests.test_native_snap_invalid_returns import produce, publish


def _native_fixture(module, tmp_path, *, uncompared):
    report = publish(produce([(None if uncompared else 90, True, 100, "holds")]))
    rows = [module.compact_case(case, {}) for case in report["cases"]]
    # Exercise complete legacy-corpus preservation with no inline source rows.
    report["cases"] = []
    config = _write_fixture(module, tmp_path, report=report, rows=rows)
    module.REPORTS = tmp_path / "absent-reports"
    return config, rows


@pytest.mark.parametrize("uncompared", [True, False], ids=["missing", "spurious"])
def test_check_rejects_comparison_status_drift_from_native_snap(tmp_path, uncompared):
    module = _load_module()
    config, rows = _native_fixture(module, tmp_path, uncompared=uncompared)
    assert module.check_suite_artifacts("test-suite", config)[0] == []
    [mismatch] = rows[0]["m"]
    if uncompared:
        assert mismatch.pop("u") is True
    else:
        mismatch["u"] = True
    chunk = module.OUT_ROOT / "test-suite" / "chunk-0.json"
    chunk.write_text(json.dumps(rows))

    problems, _stats = module.check_suite_artifacts("test-suite", config)

    assert any("comparison status" in problem for problem in problems), problems


@pytest.mark.parametrize("uncompared", [True, False], ids=["missing", "spurious"])
def test_preservation_rejects_comparison_status_drift_without_writes(tmp_path, uncompared):
    module = _load_module()
    config, rows = _native_fixture(module, tmp_path, uncompared=uncompared)
    corpus = module.OUT_ROOT / "test-suite"
    assert "preserve" in module.emit_suite("test-suite", config)
    if uncompared:
        rows[0]["m"][0].pop("u")
    else:
        rows[0]["m"][0]["u"] = True
    (corpus / "chunk-0.json").write_text(json.dumps(rows))
    before = {path.name: path.read_bytes() for path in corpus.iterdir()}

    with pytest.raises(ValueError, match="cannot preserve.*comparison status"):
        module.emit_suite("test-suite", config)

    assert {path.name: path.read_bytes() for path in corpus.iterdir()} == before


@settings(max_examples=40, deadline=None, derandomize=True)
@given(flags=st.lists(st.booleans(), min_size=1, max_size=8))
def test_property_compact_payload_parity_includes_comparison_status(tmp_path_factory, flags):
    """Native verdicts validate after compaction; flipped verdicts never do."""
    module = _load_module()
    report = publish(produce([
        (None if flag else 90, True, 100, "holds") for flag in flags
    ]))
    rows = [module.compact_case(case, {}) for case in report["cases"]]
    report["cases"] = []
    directory = tmp_path_factory.mktemp("comparison-status")
    config = _write_fixture(module, directory, report=report, rows=rows)
    assert module.check_suite_artifacts("test-suite", config)[0] == []

    for row in rows:
        [mismatch] = row["m"]
        mismatch["u"] = not mismatch.get("u", False)
    chunk = module.OUT_ROOT / "test-suite" / "chunk-0.json"
    chunk.write_text(json.dumps(rows))

    problems, _stats = module.check_suite_artifacts("test-suite", config)
    assert any("comparison status" in problem for problem in problems), problems
