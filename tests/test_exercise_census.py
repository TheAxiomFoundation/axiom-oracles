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


def test_census_counts_bound_execution_inputs_as_case_evidence(tmp_path, monkeypatch):
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
    assert panel["comparison_units"] == 39_600
    assert panel["population_commitment"] == "grouped-aggregate-only"
    assert panel["varied_fields"] == 3
    assert panel["constant_fields"] == 11
    assert panel["bridge_audited"] is True
    assert panel["per_case_evidence_committed"] is False
    assert panel["exercised"] is False

    schedule = rows["us-tariff-schedule"]
    assert schedule["cases_scanned"] == 19_118_619
    assert schedule["varied_fields"] == 34
    assert schedule["constant_fields"] == 26
    assert schedule["bridge_audited"] is True
    assert schedule["per_case_evidence_committed"] is True
    assert schedule["exercised"] is True
    assert schedule["evidence_fields"]["entry_is_china_301_2024_action"] == {
        "distinct": 1,
        "state": "constant",
    }


def test_panel_unit_count_transfer_remains_grouped_aggregate_only() -> None:
    census = _load_census()
    receipt = json.loads(
        (
            REPO_ROOT / "axiom_oracles/bridges/exercise_receipts/us-tariff-panel.json"
        ).read_text()
    )
    report = json.loads(
        (
            REPO_ROOT / "dashboard/public/data/axiom-yale-us-tariff-panel.json"
        ).read_text()
    )
    report["cases"][0]["unit_count"] += 1
    report["cases"][1]["unit_count"] -= 1

    census._validate_panel_group_aggregate(
        receipt, report, receipt_name="unit-transfer-mutant.json"
    )

    assert (
        census._receipt_commits_per_case_evidence(receipt, receipt["evidence_fields"])
        is False
    )


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
            "evidence_artifacts": [{"path": "artifact.json", "sha256": "0" * 64}],
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


def _tariff_fixture(tmp_path: Path):
    spec = importlib.util.spec_from_file_location(
        "_census_tariff_fixture",
        REPO_ROOT / "tests/test_build_us_tariff_exercise_receipt.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    producer, repo, _shard = module._fixture(tmp_path, chapter_count=100)
    receipt = producer.build_receipt(repo_root=repo)
    _write_json(repo / producer.RECEIPT_REL, receipt)
    return producer, repo, receipt


def _use_tariff_fixture(census, monkeypatch, producer, repo):
    monkeypatch.setattr(census, "REPO_ROOT", repo)
    monkeypatch.setattr(
        census, "EXERCISE_RECEIPT_DIR", repo / producer.RECEIPT_REL.parent
    )


def test_tariff_census_reaudits_current_bridge_without_external_bodies(
    tmp_path, monkeypatch
):
    census = _load_census()
    producer, repo, _receipt = _tariff_fixture(tmp_path)
    _use_tariff_fixture(census, monkeypatch, producer, repo)
    monkeypatch.setattr(census, "MANIFEST_STRICT_CLEAN", {producer.SUITE: False})
    path_open = Path.open

    def no_external_body(path, *args, **kwargs):
        assert path.suffix != ".gz", f"census tried to reopen external body: {path}"
        return path_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", no_external_body)
    row = census._committed_exercise_rows()[producer.SUITE]
    assert row["cases_scanned"] == 100
    assert row["varied_fields"] == 0
    assert row["constant_fields"] == 20
    assert row["bridge_audited"] is True
    assert row["exercised"] is True
    assert (
        row["bridge_manifest_sha256"]
        == hashlib.sha256((repo / producer.BRIDGE_REL).read_bytes()).hexdigest()
    )


def test_tariff_census_cannot_reuse_a_stale_clean_bridge_verdict(tmp_path, monkeypatch):
    census = _load_census()
    producer, repo, receipt = _tariff_fixture(tmp_path)
    _use_tariff_fixture(census, monkeypatch, producer, repo)
    monkeypatch.setattr(census, "MANIFEST_STRICT_CLEAN", {producer.SUITE: True})
    bridge_path = repo / producer.BRIDGE_REL
    bridge = json.loads(bridge_path.read_text())
    bridge["population"]["pin_required"] = False
    _write_json(bridge_path, bridge)
    receipt["evidence_artifacts"][-1]["sha256"] = hashlib.sha256(
        bridge_path.read_bytes()
    ).hexdigest()
    _write_json(repo / producer.RECEIPT_REL, receipt)
    row = census._committed_exercise_rows()[producer.SUITE]
    assert row["bridge_audited"] is False
    assert row["bridge_manifest_sha256"] is None
    assert row["exercised"] is False


@pytest.mark.parametrize(
    "mutation", ["cases", "drop_input", "varied_constant", "too_many_distinct"]
)
def test_tariff_census_rejects_self_asserted_counts_and_catalog(
    tmp_path, monkeypatch, mutation
):
    census = _load_census()
    producer, repo, receipt = _tariff_fixture(tmp_path)
    _use_tariff_fixture(census, monkeypatch, producer, repo)
    messages = {
        "cases": "case count differs",
        "drop_input": "field catalog differs",
        "varied_constant": "construction constant varied",
        "too_many_distinct": "invalid exercise distinct count",
    }
    if mutation == "cases":
        receipt["cases"] = 777
    elif mutation == "drop_input":
        del receipt["evidence_fields"]["flag_a"]
    elif mutation == "varied_constant":
        receipt["evidence_fields"]["neutral_fact"] = {"distinct": 2, "state": "varied"}
    else:
        receipt["evidence_fields"]["flag_a"] = {
            "distinct": receipt["cases"] + 1,
            "state": "varied",
        }
    _write_json(repo / producer.RECEIPT_REL, receipt)
    with pytest.raises(ValueError, match=messages[mutation]):
        census._committed_exercise_rows()


@pytest.mark.parametrize("restore", [False, True], ids=["drift", "aba"])
def test_tariff_census_guard_covers_the_fresh_bridge_audit(
    tmp_path, monkeypatch, restore
):
    census = _load_census()
    producer, repo, _receipt = _tariff_fixture(tmp_path)
    _use_tariff_fixture(census, monkeypatch, producer, repo)
    audit = census._current_tariff_bridge_audit
    path = repo / producer.RECEIPT_REL
    original = path.read_bytes()

    def mutate_after_audit(*args):
        result = audit(*args)
        path.write_bytes(original + b"\n")
        if restore:
            path.write_bytes(original)
        return result

    monkeypatch.setattr(census, "_current_tariff_bridge_audit", mutate_after_audit)
    with pytest.raises(ValueError, match="evidence changed"):
        census._committed_exercise_rows()


@pytest.mark.parametrize(
    "distinct,state",
    [
        (None, None),
        (0, None),
        (-1, None),
        (True, "constant"),
        (1.0, "constant"),
    ],
)
def test_committed_census_rejects_invalid_distinct_counts(
    tmp_path, monkeypatch, distinct, state
):
    census = _load_census()
    receipt_dir = tmp_path / "axiom_oracles/bridges/exercise_receipts"
    report = tmp_path / "report.json"
    report_body = _write_json(report, {"suite": "fixture"})
    report_sha = hashlib.sha256(report_body).hexdigest()
    _write_json(
        receipt_dir / "fixture.json",
        {
            "schema": census.EXERCISE_RECEIPT_SCHEMA,
            "suite": "fixture",
            "cases": 1,
            "report": "report.json",
            "report_sha256": report_sha,
            "evidence_artifacts": [{"path": "report.json", "sha256": report_sha}],
            "evidence_fields": {"x": {"distinct": distinct, "state": state}},
        },
    )
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(census, "EXERCISE_RECEIPT_DIR", receipt_dir)
    with pytest.raises(ValueError, match="invalid distinct count"):
        census._committed_exercise_rows()


@pytest.mark.parametrize(
    ("target", "raw"),
    [
        ("report", "../outside.json"),
        ("report", "/tmp/outside.json"),
        ("artifact", "../outside.json"),
        ("artifact", "/tmp/outside.json"),
    ],
)
def test_committed_receipt_paths_cannot_escape_repository(
    tmp_path: Path, monkeypatch, target: str, raw: str
) -> None:
    census = _load_census()
    receipt_dir = tmp_path / "axiom_oracles/bridges/exercise_receipts"
    report = tmp_path / "report.json"
    report_body = _write_json(report, {"suite": "fixture"})
    report_sha = hashlib.sha256(report_body).hexdigest()
    receipt = {
        "schema": census.EXERCISE_RECEIPT_SCHEMA,
        "suite": "fixture",
        "cases": 1,
        "report": "report.json",
        "report_sha256": report_sha,
        "evidence_artifacts": [{"path": "report.json", "sha256": report_sha}],
        "evidence_fields": {"x": {"distinct": 1, "state": "constant"}},
    }
    if target == "report":
        receipt["report"] = raw
    else:
        receipt["evidence_artifacts"][0]["path"] = raw
    _write_json(receipt_dir / "fixture.json", receipt)
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(census, "EXERCISE_RECEIPT_DIR", receipt_dir)
    with pytest.raises(ValueError, match="invalid repository-relative path"):
        census._committed_exercise_rows()


def test_duplicate_committed_receipt_suite_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    census = _load_census()
    receipt_dir = tmp_path / "axiom_oracles/bridges/exercise_receipts"
    report = tmp_path / "report.json"
    report_body = _write_json(report, {"suite": "fixture"})
    report_sha = hashlib.sha256(report_body).hexdigest()
    receipt = {
        "schema": census.EXERCISE_RECEIPT_SCHEMA,
        "suite": "fixture",
        "cases": 1,
        "report": "report.json",
        "report_sha256": report_sha,
        "evidence_artifacts": [{"path": "report.json", "sha256": report_sha}],
        "evidence_fields": {"x": {"distinct": 1, "state": "constant"}},
    }
    _write_json(receipt_dir / "a.json", receipt)
    _write_json(receipt_dir / "b.json", receipt)
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(census, "EXERCISE_RECEIPT_DIR", receipt_dir)
    with pytest.raises(ValueError, match="duplicate committed exercise suite"):
        census._committed_exercise_rows()


def test_build_census_rejects_receipt_collision_with_derived_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    census = _load_census()
    report_path = tmp_path / "report.json"
    report = {"suite": "fixture", "cases": []}
    _write_json(report_path, report)
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        census, "_iter_suite_reports", lambda: [("fixture", report, report_path)]
    )
    monkeypatch.setattr(
        census,
        "_census_suite",
        lambda *_args: {
            "report": "report.json",
            "evidence_source": "chunks",
            "evidence_fields": {"x": {"distinct": 1, "state": "constant"}},
        },
    )
    monkeypatch.setattr(
        census,
        "_committed_exercise_rows",
        lambda: {
            "fixture": {
                "report": "report.json",
                "per_case_evidence_committed": True,
            }
        },
    )
    with pytest.raises(ValueError, match="collides with independently derived"):
        census.build_census()
