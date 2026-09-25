"""Focused tests for lightweight census evidence binding."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from axiom_oracles.evidence import CHUNK_INDEX_SCHEMA_VERSION


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_census():
    spec = importlib.util.spec_from_file_location(
        "exercise_census_under_test",
        REPO_ROOT / "scripts" / "exercise_census.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload) -> bytes:
    rendered = json.dumps(payload, sort_keys=True).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rendered)
    return rendered


def test_census_records_bound_cardinality_without_a_second_strict_pass(
    tmp_path, monkeypatch
):
    census = _load_census()
    data_dir = tmp_path / "data"
    cases_dir = data_dir / "cases"
    suite = "fixture-suite"
    report = {
        "suite": suite,
        "summary": {
            "comparison_count": 2,
            "match_count": 1,
            "mismatch_count": 1,
        },
        "cases": [],
    }
    report_path = data_dir / "report.json"
    report_bytes = _write_json(report_path, report)
    chunk_path = cases_dir / suite / "chunk-000.json"
    chunk_bytes = _write_json(
        chunk_path,
        [
            {"id": "one", "i": [{"n": "x", "v": 1}]},
            {"id": "two", "i": [{"n": "x", "v": 2}]},
        ],
    )
    _write_json(
        cases_dir / suite / "index.json",
        {
            "schema_version": CHUNK_INDEX_SCHEMA_VERSION,
            "suite": suite,
            "report_path": report_path.resolve().as_posix(),
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "chunks": [
                {
                    "name": chunk_path.name,
                    "sha256": hashlib.sha256(chunk_bytes).hexdigest(),
                    "cases": 2,
                }
            ],
        },
    )
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(census, "CASES_DIR", cases_dir)

    row = census._census_suite(suite, report, report_path)

    assert row["binding"] == "bound"
    assert row["binding_defects"] == []
    assert row["reconciliation"] == "cardinality"
    assert row["cases_scanned"] == 2
    assert row["chunk_manifest"][0]["cases"] == 2
    assert row["threshold_straddle"]["mode"] == "unavailable"
    assert row["exercised"] is False


def test_unbound_or_nonreconciling_chunks_do_not_block_census(tmp_path, monkeypatch):
    census = _load_census()
    data_dir = tmp_path / "data"
    cases_dir = data_dir / "cases"
    suite = "fixture-suite"
    report = {
        "suite": suite,
        "summary": {
            "comparison_count": 4,
            "match_count": 4,
            "mismatch_count": 0,
        },
        "cases": [],
    }
    report_path = data_dir / "report.json"
    _write_json(report_path, report)
    _write_json(
        cases_dir / suite / "chunk-000.json",
        [{"id": "one"}, {"id": "two"}],
    )
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(census, "CASES_DIR", cases_dir)

    row = census._census_suite(suite, report, report_path)

    assert row["binding"] == "unbound"
    assert any(
        "index" in defect and "missing" in defect for defect in row["binding_defects"]
    )
    assert row["reconciliation"] == "none"
    assert row["cases_scanned"] == 2


def test_census_counts_bound_execution_inputs_as_case_evidence(
    tmp_path, monkeypatch
):
    census = _load_census()
    data_dir = tmp_path / "data"
    cases_dir = data_dir / "cases"
    suite = "fixture-suite"
    report = {
        "suite": suite,
        "summary": {
            "comparison_count": 2,
            "match_count": 2,
            "mismatch_count": 0,
        },
        "cases": [],
    }
    report_path = data_dir / "report.json"
    report_bytes = _write_json(report_path, report)
    chunk_path = cases_dir / suite / "chunk-0.json"
    chunk_bytes = _write_json(
        chunk_path,
        [
            {
                "id": "one",
                "execution": {
                    "schema_version": "axiom_oracles.case_execution.v1",
                    "axiom_inputs": {"amount": 1, "constant": False},
                },
            },
            {
                "id": "two",
                "execution": {
                    "schema_version": "axiom_oracles.case_execution.v1",
                    "axiom_inputs": {"amount": 2, "constant": False},
                },
            },
        ],
    )
    _write_json(
        cases_dir / suite / "index.json",
        {
            "schema_version": CHUNK_INDEX_SCHEMA_VERSION,
            "suite": suite,
            "report_path": report_path.resolve().as_posix(),
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "chunks": [
                {
                    "name": chunk_path.name,
                    "sha256": hashlib.sha256(chunk_bytes).hexdigest(),
                    "cases": 2,
                }
            ],
        },
    )
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(census, "CASES_DIR", cases_dir)

    row = census._census_suite(suite, report, report_path)

    assert row["evidence_fields"] == {
        "amount": {"distinct": 2, "state": "varied"},
        "constant": {"distinct": 1, "state": "constant"},
    }
    assert row["varied_fields"] == 1
    assert row["constant_fields"] == 1


def test_unsafe_suite_name_cannot_escape_the_case_root(tmp_path, monkeypatch):
    census = _load_census()
    data_dir = tmp_path / "data"
    report_path = data_dir / "report.json"
    report = {
        "suite": "../outside",
        "summary": {
            "comparison_count": 1,
            "match_count": 1,
            "mismatch_count": 0,
        },
        "cases": [],
    }
    _write_json(report_path, report)
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(census, "CASES_DIR", data_dir / "cases")

    row = census._census_suite("../outside", report, report_path)

    assert row["cases_scanned"] == 0
    assert row["binding"] == "unbound"
    assert any("safe path component" in defect for defect in row["binding_defects"])


def test_committed_tariff_exercise_receipts_are_strict_bound() -> None:
    census = _load_census()

    rows = census._committed_exercise_rows()

    panel = rows["us-tariff-panel"]
    assert panel["cases_scanned"] == 122
    assert panel["varied_fields"] == 3
    assert panel["constant_fields"] == 11
    assert panel["bridge_audited"] is True
    assert panel["per_case_evidence_committed"] is True
    assert panel["threshold_straddle"]["mode"] == "unavailable"
    assert panel["exercised"] is False

    schedule = rows["us-tariff-schedule"]
    assert schedule["cases_scanned"] == 19_118_619
    assert schedule["varied_fields"] == 15
    assert schedule["constant_fields"] == 15
    assert schedule["bridge_audited"] is True
    assert schedule["per_case_evidence_committed"] is True
    assert schedule["threshold_straddle"]["mode"] == "unavailable"
    assert schedule["exercised"] is False
    assert schedule["evidence_fields"]["entry_is_china_301_2024_action"] == {
        "distinct": 1,
        "state": "constant",
    }


def test_committed_exercise_receipt_rejects_artifact_hash_drift(
    tmp_path, monkeypatch
) -> None:
    census = _load_census()
    receipt_dir = tmp_path / "axiom_oracles/bridges/exercise_receipts"
    report = tmp_path / "report.json"
    artifact = tmp_path / "artifact.json"
    _write_json(report, {"suite": "fixture"})
    _write_json(artifact, {"rows": 1})
    _write_json(
        receipt_dir / "fixture.json",
        {
            "schema": census.EXERCISE_RECEIPT_SCHEMA,
            "suite": "fixture",
            "cases": 1,
            "report": "report.json",
            "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
            "evidence_artifacts": [
                {"path": "artifact.json", "sha256": "0" * 64}
            ],
            "evidence_fields": {"x": {"distinct": 1, "state": "constant"}},
        },
    )
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(census, "EXERCISE_RECEIPT_DIR", receipt_dir)

    try:
        census._committed_exercise_rows()
    except ValueError as exc:
        assert "evidence artifact drifted" in str(exc)
    else:  # pragma: no cover - mutant guard
        raise AssertionError("artifact hash drift was accepted")


def test_global_census_records_separate_nz_view_threshold_verdicts(monkeypatch):
    """A unified report's views cannot inherit one another's threshold result."""
    from scripts import threshold_straddle

    census = _load_census()
    report_path = REPO_ROOT / "dashboard/public/data/nz-treasury-incomeexplorer.json"
    report = json.loads(report_path.read_text())
    calls = []

    def compute(compiled, traces, *, view, roots):
        calls.append((view, roots))
        assert hashlib.sha256(compiled).hexdigest() == (
            traces["compiled_program"]["artifact_sha256"]
        )
        return {"mode": "computed", "complete": view != "nz/income-tax"}

    monkeypatch.setattr(threshold_straddle, "compute_threshold_straddle", compute)
    monkeypatch.setattr(
        census, "_iter_suite_reports", lambda: [(report["suite"], report, report_path)]
    )
    monkeypatch.setattr(census, "_committed_exercise_rows", dict)

    result = census.build_census()

    assert result["suites"] == {}
    views = result["views"][report["suite"]]
    assert set(views) == set(report["experiment"]["views"])
    assert len(calls) == len(views)
    for view, roots in calls:
        assert roots == report["experiment"]["views"][view]["requested_output_roots"]
        assert views[view]["exercised"] is (view != "nz/income-tax")
    assert views["nz/income-tax"]["evaluations_scanned"] == 91


@pytest.mark.parametrize(
    ("relative_path", "marker"),
    [
        (
            "conformance/executable/nz-treasury-incomeexplorer/compiled-program.json",
            "compiled artifact bytes disagree with executable receipt",
        ),
        (
            "comparisons/nz-treasury-incomeexplorer/evaluation-traces.json",
            "evaluation trace bytes changed",
        ),
    ],
)
def test_threshold_loader_rechecks_artifact_bytes(relative_path, marker, monkeypatch):
    """A preceding valid receipt cannot hide subsequent byte drift."""
    from scripts import threshold_straddle

    census = _load_census()
    report_path = REPO_ROOT / "dashboard/public/data/nz-treasury-incomeexplorer.json"
    report = json.loads(report_path.read_text())
    view = "nz/income-tax"
    receipt = report["experiment"]["views"][view]
    calls = []

    def compute(*args, **kwargs):
        calls.append(True)
        return {"mode": "computed", "complete": True}

    monkeypatch.setattr(threshold_straddle, "compute_threshold_straddle", compute)
    assert census._threshold_straddle_for_view(report, view, receipt)["complete"] is True
    original = Path.read_bytes
    target = (REPO_ROOT / relative_path).resolve()

    def drift(path):
        raw = original(path)
        return raw + b"\n" if path.resolve() == target else raw

    monkeypatch.setattr(Path, "read_bytes", drift)
    result = census._threshold_straddle_for_view(report, view, receipt)

    assert result["mode"] == "unavailable"
    assert marker in result["reason"]
    assert len(calls) == 1


def test_threshold_loader_rejects_comparison_artifact_substitution(monkeypatch):
    from scripts import threshold_straddle

    census = _load_census()
    report_path = REPO_ROOT / "dashboard/public/data/nz-treasury-incomeexplorer.json"
    report = json.loads(report_path.read_text())
    report["compiled_program"]["artifact_sha256"] = "0" * 64

    def unexpected(*args, **kwargs):
        raise AssertionError("an unbound artifact reached the interpreter")

    monkeypatch.setattr(threshold_straddle, "compute_threshold_straddle", unexpected)
    view = "nz/income-tax"
    result = census._threshold_straddle_for_view(
        report, view, report["experiment"]["views"][view]
    )

    assert result["mode"] == "unavailable"
    assert "disagree with comparison report" in result["reason"]
