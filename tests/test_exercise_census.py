"""Focused tests for lightweight census evidence binding."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

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
