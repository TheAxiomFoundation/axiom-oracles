"""Registry provenance stamping keeps this run's relation diagnostics."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
import subprocess

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st


def _registry():
    path = Path(__file__).parents[1] / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("diagnostic_registry", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _diagnostics(count=2):
    return {
        "count": count,
        "by_relation": {"members": count},
        "samples": [{"relation": "members", "tuple": ["member", "owner"]}],
    }


def _fresh_provenance():
    return {"generated_at": "2026-10-11T00:00:00Z", "run_kind": "manual"}


def test_stamp_preserves_only_relation_diagnostics_from_report(tmp_path):
    registry = _registry()
    path = tmp_path / "report.json"
    diagnostics = _diagnostics()
    fresh = _fresh_provenance()
    before = deepcopy(fresh)
    path.write_text(json.dumps({"suite": "test", "provenance": {
        "generated_at": "stale", "obsolete_runner_key": True,
        "relation_binding_diagnostics": diagnostics,
    }}))

    registry._stamp_report_provenance(path, fresh, preserve_runner_provenance=False)

    assert json.loads(path.read_text())["provenance"] == {
        **fresh, "relation_binding_diagnostics": diagnostics,
    }
    assert fresh == before


@pytest.mark.parametrize("artifact", ["full", "dashboard"])
def test_registry_publication_keeps_relation_diagnostics(tmp_path, monkeypatch, artifact):
    registry = _registry()
    diagnostics = _diagnostics()
    fresh = _fresh_provenance()
    config = {
        "name": "diagnostic-suite",
        "runner": {"type": "test-diagnostic-runner", "parameters": {"sample_size": 0}},
        "artifacts": {"report_basename": "diagnostic-suite"},
        "dashboard": {"filename": "diagnostic-suite.json"},
    }
    monkeypatch.setattr(registry, "_load_comparison", lambda _name: config)
    monkeypatch.setattr(registry, "_verify_declared_pins", lambda _config: None)
    monkeypatch.setattr(registry, "_build_run_provenance", lambda *_args: deepcopy(fresh))
    monkeypatch.setattr(registry, "_merge_dispositions", lambda report: report)
    dashboard = tmp_path / "dashboard"
    monkeypatch.setattr(registry, "DASHBOARD_DATA_DIR", dashboard)

    def runner(_config, output):
        output.write_text(json.dumps({
            "schema_version": "axiom.comparison_report.v2", "suite": "test",
            "cases": [], "mismatches": [], "summary": {"mismatch_count": 0},
            "provenance": {"obsolete_runner_key": True,
                           "relation_binding_diagnostics": diagnostics},
        }))

    monkeypatch.setitem(registry.RUNNERS, "test-diagnostic-runner", runner)
    reports = tmp_path / "reports"
    monkeypatch.setattr("sys.argv", [
        "run_comparison.py", "diagnostic-suite", "--output-dir", str(reports),
    ])

    assert registry.main() == 0
    [full] = reports.glob("*.json")
    path = full if artifact == "full" else dashboard / "diagnostic-suite.json"
    assert json.loads(path.read_text())["provenance"] == {
        **fresh, "relation_binding_diagnostics": diagnostics,
    }


@pytest.mark.parametrize("runner_type", [
    "axiom-encode-tax-ecps-compare", "axiom-encode-uk-efrs-compare",
])
def test_native_report_adaptation_keeps_relation_diagnostics(tmp_path, runner_type):
    registry = _registry()
    diagnostics = _diagnostics()
    path = tmp_path / "native-report.json"
    path.write_text(json.dumps({"provenance": {
        "relation_binding_diagnostics": diagnostics,
    }}))
    adapted = registry._adapt_to_v2(path, runner_type, {}, suite="diagnostic-suite")
    assert adapted["provenance"]["relation_binding_diagnostics"] == diagnostics


@pytest.mark.parametrize("sidecar", ["diagnostics", "identity-only", "missing", "malformed"])
def test_snap_csv_runner_transfers_only_sidecar_diagnostics(tmp_path, monkeypatch, sidecar):
    registry = _registry()
    encoder = tmp_path / "encoder"
    encoder.mkdir()
    diagnostics = _diagnostics(7)
    temporary_directory = registry.tempfile.TemporaryDirectory
    monkeypatch.setattr(registry.tempfile, "TemporaryDirectory", lambda **kwargs: (
        temporary_directory(dir=tmp_path, **kwargs)
    ))

    def run(cmd, *, check, cwd):
        path = Path(cmd[cmd.index("--write-csv") + 1])
        path.write_text(
            "spm_unit_id,household_id,pe_snap,axiom_snap_allotment,"
            "difference,absolute_difference,match,pe_snap_eligible,axiom_snap_eligible\n"
            "1,2,0,0,0,0,True,True,True\n"
        )
        identity = {"source": "private-dataset-source", "revision": "private-revision"}
        if sidecar == "diagnostics":
            identity["relation_binding_diagnostics"] = diagnostics
        if sidecar != "missing":
            path.with_suffix(path.suffix + ".dataset_identity.json").write_text(
                "invalid JSON" if sidecar == "malformed" else json.dumps(identity)
            )
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(registry.subprocess, "run", run)
    path = tmp_path / "snap-report.json"
    registry._run_axiom_encode_snap_ecps_compare(
        {"axiom_encode_repo": str(encoder), "parameters": {"jurisdiction": "us-co"}},
        path,
    )
    report = json.loads(path.read_text())
    if sidecar == "diagnostics":
        assert report["provenance"] == {"relation_binding_diagnostics": diagnostics}
    else:
        assert "provenance" not in report
    assert "dataset_identity" not in report
    assert "private-dataset-source" not in path.read_text()
    assert "private-revision" not in path.read_text()
    assert report["case_count"] == 1


@settings(max_examples=16, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(count=st.integers(min_value=1, max_value=200), stale=st.dictionaries(
    st.text(alphabet="abcdefgh", min_size=1, max_size=8), st.integers(), max_size=8,
))
def test_stamping_preserves_diagnostic_counts_without_stale_keys(tmp_path, count, stale):
    # Every example replaces the report; no example inherits another's data.
    registry = _registry()
    diagnostics = _diagnostics(count)
    fresh = _fresh_provenance()
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"provenance": {
        **stale, "relation_binding_diagnostics": diagnostics,
    }}))
    registry._stamp_report_provenance(path, fresh)
    assert json.loads(path.read_text())["provenance"] == {
        **fresh, "relation_binding_diagnostics": diagnostics,
    }
