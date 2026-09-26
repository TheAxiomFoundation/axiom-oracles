"""Replay routing, fetch CLI, and registry provenance fail closed."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from axiom_oracles.adapters.taxsim import pins, recorded
from axiom_oracles.cli import cli

ROOT = Path(__file__).resolve().parents[1]


def _registry():
    spec = importlib.util.spec_from_file_location("recorded_registry_test", ROOT / "scripts/run_comparison.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config():
    return yaml.safe_load((ROOT / "comparisons/taxsim-emulator-ecps-2024.yaml").read_text())


@pytest.mark.parametrize("block", [{}, None, False, "", []])
def test_malformed_recorded_configuration_cannot_fall_back_to_live(monkeypatch, tmp_path, block):
    module = _registry()
    config = _config()
    config["runner"]["parameters"]["recorded_release"] = block
    monkeypatch.setenv("AXIOM_TAXSIM_CSV", str(tmp_path / "inputs.csv"))
    monkeypatch.setattr(module, "_resolve_pe_oracle_pins",
                        lambda params: pytest.fail("Replay configuration selected live engine setup"))
    monkeypatch.setattr(module.subprocess, "run",
                        lambda *args, **kwargs: pytest.fail("Malformed replay launched a process"))
    with pytest.raises(SystemExit, match="recorded_release"):
        module._run_axiom_oracles_compare(config["runner"], tmp_path / "report.json")


@pytest.mark.parametrize("change", [
    {"sha256_by_year": {}}, {"tag": ""}, {"repo": ""},
    {"path": "/tmp/release"}, {"unknown_key": "ignored?"},
])
def test_recorded_suite_requires_unambiguous_path_and_explicit_pin(monkeypatch, tmp_path, change):
    module = _registry()
    params = _config()["runner"]["parameters"]
    params["recorded_release"].update(change)
    monkeypatch.setenv("AXIOM_TAXSIM_RECORDED_RELEASE", str(tmp_path))
    with pytest.raises(SystemExit, match="recorded_release"):
        module._recorded_release_cli_args(params)


def _pinned_downloads(monkeypatch):
    csv_bytes = b"taxsimid,source,fiitax,siitax\n1,taxsim,10,0\n1,policyengine,11,0\n"
    sha = hashlib.sha256(csv_bytes).hexdigest()
    provenance = {
        "year": 2024, "outputSha256": sha, "sourceSha256": "a" * 64,
        "taxsimBinarySha256": pins.resolve_binary(0, 2024, "linux", "dashboard-2026-09"),
        "emulatorCommit": "b" * 40, "policyengineUsVersion": "2.6.17",
        "policyengineCoreVersion": "3.32.6", "assumeW2Wages": True,
        "disableSalt": False, "policyengineOutputDetail": 5,
    }
    provenance_bytes = json.dumps(provenance).encode()
    monkeypatch.setattr(recorded, "SHA256_BY_YEAR", {2024: sha})
    monkeypatch.setattr(recorded, "PROVENANCE_SHA256_BY_YEAR",
                        {2024: hashlib.sha256(provenance_bytes).hexdigest()})
    return {"comparison_results_2024.csv": csv_bytes, "provenance_2024.json": provenance_bytes}


def test_fetch_release_cli_downloads_built_in_pinned_assets(monkeypatch, tmp_path):
    downloads = _pinned_downloads(monkeypatch)
    urls = []

    def download(url):
        urls.append(url)
        return downloads[url.rsplit("/", 1)[-1]]

    monkeypatch.setattr(recorded, "_download", download)
    result = CliRunner().invoke(cli, [
        "taxsim", "fetch-release", "--repo", recorded.DEFAULT_REPO,
        "--tag", recorded.DEFAULT_TAG, "--dir", str(tmp_path / "release"),
    ])
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.output)) == len(urls) == 2
    for name, data in downloads.items():
        assert (tmp_path / "release" / name).read_bytes() == data
        assert f"https://github.com/{recorded.DEFAULT_REPO}/releases/download/{recorded.DEFAULT_TAG}/{name}" in urls


def test_fetch_release_cli_keeps_no_bad_downloads(monkeypatch, tmp_path):
    _pinned_downloads(monkeypatch)
    monkeypatch.setattr(recorded, "_download", lambda url: b"tampered")
    destination = tmp_path / "release"
    result = CliRunner().invoke(cli, [
        "taxsim", "fetch-release", "--tag", recorded.DEFAULT_TAG, "--dir", str(destination),
    ])
    assert result.exit_code != 0
    assert "sha256 mismatch" in result.output
    assert not destination.exists()


def test_registry_provenance_uses_recorded_versions_and_binary_identity(tmp_path):
    module = _registry()
    config = _config()
    identity = {
        "repo": recorded.DEFAULT_REPO, "tag": recorded.DEFAULT_TAG,
        "file": "comparison_results_2024.csv", "sha256": recorded.SHA256_BY_YEAR[2024],
        "provenance": {"emulatorCommit": "b" * 40},
    }
    taxsim_identity = {"pin_profile": "dashboard-2026-09", "binaries": [
        {"sha256": "c" * 64, "platform": "linux", "rows": 7, "scope": "default",
         "build": "cd2026090910", "build_observed": None},
    ]}
    report = {
        "recorded_release": identity,
        "engine_identity": {"taxsim": taxsim_identity, "policyengine": {
            "policyengineUsVersion": "2.6.17", "policyengineCoreVersion": "3.32.6",
            "emulatorCommit": "b" * 40,
        }},
        "engines": {"versions": {"policyengine_us": "2.6.17", "policyengine_core": "3.32.6"}},
        "dataset_identity": {"source": "taxsim-csv", "sha256": "a" * 64, "rows": 7},
    }
    output = tmp_path / "report.json"
    output.write_text(json.dumps(report))
    provenance = module._build_run_provenance(config, config["runner"]["type"], output)
    assert provenance["oracle"]["recorded_release"] == identity
    assert provenance["oracle"]["taxsim_binaries"] == taxsim_identity["binaries"]
    assert provenance["oracle"]["policyengine_us"] == "2.6.17"
    assert provenance["oracle"]["policyengine_core"] == "3.32.6"
    assert provenance["dataset"]["sha256"] == "a" * 64
    module._stamp_report_provenance(output, provenance)
    stamped = json.loads(output.read_text())
    assert stamped["engines"]["versions"] == report["engines"]["versions"]
    assert stamped["recorded_release"] == report["recorded_release"]
