"""Manual ledger reports remain checkable without dashboard publication."""

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from axiom_oracles.comparison.dispositions import apply_dispositions
from axiom_oracles.comparison.report_io import (
    load_report,
    read_report_text,
    registered_report_paths,
    unpublished_registered_suites,
    write_report,
)

ROOT = Path(__file__).resolve().parents[1]


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(tmp_path):
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    path = tmp_path / "reports" / "taxsim-emulator" / "manual.json.gz"
    (comparisons / "manual.yaml").write_text(yaml.safe_dump({
        "name": "manual", "ci": "manual",
        "artifacts": {"report_path": str(path.relative_to(tmp_path))},
    }))
    report = {
        "schema_version": "axiom.comparison_report.v2", "suite": "manual",
        "engines": {"left": "policyengine", "right": "taxsim"},
        "summary": {"comparison_count": 1, "match_count": 0, "mismatch_count": 1},
        "mismatches": [{
            "case_id": "a", "concept": "us:test#tax", "kind": "amount_difference",
            "left": 10, "right": 0, "difference": 10,
            "aux": {"left": {"niit": 10}, "right": {"niit": 0}},
        }],
    }
    document = {
        "schema": "axiom_oracles.dispositions.v1", "suite": "manual", "entries": [{
            "id": "test", "concept": "us:test#tax", "case_id": "a",
            "disposition": "upstream_engine_gap", "attribution": "taxsim",
            "pinned": {"left": 10, "right": 0},
            "oracle_binding": {"identity_unrecorded": True},
            "expires_on_source_change": True,
            "evidence": {
                "mechanism": "Fixture difference equals the recorded auxiliary difference.",
                "row_arithmetic": [{
                    "expression": "left_aux.niit - right_aux.niit - difference", "equals": 0,
                }],
            },
        }],
    }
    write_report(path, report)
    return path, report, document


@pytest.mark.parametrize("suffix", [".json", ".json.gz"])
def test_report_roundtrip_and_deterministic_bytes(tmp_path, suffix):
    path = tmp_path / f"report{suffix}"
    report = {"suite": "test", "mismatches": [{"aux": {"left": {"niit": 1.2}}}]}
    write_report(path, report)
    first = path.read_bytes()
    assert load_report(path) == report
    write_report(path, report)
    assert path.read_bytes() == first
    if suffix.endswith(".gz"):
        assert gzip.decompress(first).decode() == json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"


def test_disposition_check_detects_aux_evidence_failure_in_registered_gzip(tmp_path):
    path, report, document = _fixture(tmp_path)
    module = _script("apply_dispositions")
    module.REPO_ROOT = tmp_path
    module.DASHBOARD_DATA_DIR = tmp_path / "dashboard" / "public" / "data"
    merged = apply_dispositions(report, document, dispositions_file="dispositions/manual.yaml")
    write_report(path, merged)
    assert module._merge_reports({"manual": document}, check=True) == ([], [], False)
    merged["mismatches"][0]["aux"]["left"]["niit"] += 1
    write_report(path, merged)
    problems, _, _ = module._merge_reports({"manual": document}, check=True)
    assert any("fails its evidence.row_arithmetic" in item for item in problems)


def test_disposition_merge_preserves_compact_gzip_and_binding_reads_it(tmp_path):
    path, report, document = _fixture(tmp_path)
    module = _script("apply_dispositions")
    module.REPO_ROOT = tmp_path
    module.DASHBOARD_DATA_DIR = tmp_path / "dashboard" / "public" / "data"
    assert module._merge_reports({"manual": document}, check=False) == ([], [], True)
    assert len(read_report_text(path).splitlines()) == 1
    assert load_report(path)["mismatches"][0]["disposition"]["id"] == "test"
    bind = _script("bind_dispositions")
    bind.REPO_ROOT = tmp_path
    bind.DASHBOARD_DATA_DIR = module.DASHBOARD_DATA_DIR
    assert bind.resolve_full_report("manual", None)[0] == path
    assert bind.resolve_full_report("manual", path)[1] == load_report(path)


def test_slim_source_pointer_verifies_compressed_bytes_and_reads_gzip(tmp_path):
    path, report, _ = _fixture(tmp_path)
    module = _script("apply_dispositions")
    module.REPO_ROOT = tmp_path
    pointer = {"path": str(path.relative_to(tmp_path)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    problems = []
    assert module._resolve_source_pointer(Path("dashboard.json"), "manual", pointer, problems) == (path, report)
    assert problems == []
    path.write_bytes(path.read_bytes() + b"tampered")
    assert module._resolve_source_pointer(Path("dashboard.json"), "manual", pointer, problems) is None
    assert "sha256 mismatch" in problems[0]


@pytest.mark.parametrize("path", ["../outside.json.gz", "/tmp/report.json", "reports/report.csv"])
def test_registered_artifact_rejects_invalid_paths(tmp_path, path):
    directory = tmp_path / "comparisons"
    directory.mkdir()
    (directory / "bad.yaml").write_text(yaml.safe_dump({"artifacts": {"report_path": path}}))
    with pytest.raises(ValueError, match="artifacts.report_path"):
        registered_report_paths(tmp_path)


def test_registered_missing_artifact_is_not_silently_skipped(tmp_path):
    path, _, _ = _fixture(tmp_path)
    path.unlink()
    module = _script("apply_dispositions")
    module.REPO_ROOT = tmp_path
    module.DASHBOARD_DATA_DIR = tmp_path / "dashboard" / "public" / "data"
    with pytest.raises(FileNotFoundError):
        list(module._reports())


def test_manual_emulator_ledger_is_outside_publishing_ratchet(tmp_path):
    _fixture(tmp_path)
    module = _script("unexplained_ratchet")
    module.REPO_ROOT = tmp_path
    module.DASHBOARD_DATA = tmp_path / "dashboard" / "public" / "data"
    module.KNOWN_CAUSES_PATH = module.DASHBOARD_DATA / "known_causes.json"
    assert module.gated_reports() == {}
    assert module.live_counts() == {}


def test_manual_ledger_is_excluded_from_case_and_overview_generators(tmp_path):
    _fixture(tmp_path)
    data = tmp_path / "dashboard" / "public" / "data"
    data.mkdir(parents=True)
    # Even a stray manifest entry must not promote an explicitly registered
    # manual ledger before its suite declares a dashboard target.
    (data / "manifest.json").write_text(json.dumps({"reports": ["manual.json"]}))
    (data / "manual.json").write_text(json.dumps({"suite": "manual", "summary": {}}))
    cases = _script("emit_case_artifacts")
    cases.REPO_ROOT = tmp_path
    cases.DASHBOARD_DATA = data
    assert cases.dashboard_suites() == {}
    overview = _script("generate_dashboard_overview")
    overview.REPO_ROOT = tmp_path
    overview.DATA = data
    assert overview.build()["reports"] == []


def test_explicit_dashboard_target_preserves_publishing_opt_in(tmp_path):
    _fixture(tmp_path)
    config = tmp_path / "comparisons" / "manual.yaml"
    assert unpublished_registered_suites(tmp_path) == {"manual"}
    doc = yaml.safe_load(config.read_text())
    doc["dashboard"] = {"filename": "manual.json"}
    config.write_text(yaml.safe_dump(doc))
    assert unpublished_registered_suites(tmp_path) == set()
