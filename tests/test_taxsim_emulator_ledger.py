"""Recorded CLI/registry integration and differential dashboard headline checks."""

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from axiom_oracles.adapters.taxsim import pins
from axiom_oracles.cli import cli
from axiom_oracles.comparison.report_io import load_report

ROOT = Path(__file__).resolve().parents[1]
FEDERAL = "us:tax/federal-income-tax#liability"
STATE = "us:tax/state-income-tax#liability"


def registry():
    spec = importlib.util.spec_from_file_location("run_comparison", ROOT / "scripts/run_comparison.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def small_release(tmp_path):
    population = tmp_path / "inputs.csv"
    population.write_text("taxsimid,year,state,mstat,pwages\n1,2023,0,2,300000\n2,2023,44,2,300000\n")
    source_sha = hashlib.sha256(population.read_bytes()).hexdigest()
    output = tmp_path / "comparison_results_2024.csv"
    with output.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["taxsimid", "year", "state", "mstat", "pwages", "source", "fiitax", "siitax", "niit"])
        for taxsimid, state in [(2, 44), (1, 0)]:
            for engine in ["taxsim", "policyengine"]:
                writer.writerow([taxsimid, 2024, state, 2, 300000, engine,
                                 1000000000 + (20 if engine == "policyengine" else 0),
                                 1000000000 + ((15 if taxsimid == 1 else 20) if engine == "policyengine" else 0), 12])
    sha = hashlib.sha256(output.read_bytes()).hexdigest()
    provenance = {
        "year": 2024, "sourceSha256": source_sha, "outputSha256": sha,
        "taxsimBinarySha256": pins.resolve_binary(0, 2024, "linux", "dashboard-2026-09"),
        "emulatorCommit": "a" * 40, "policyengineUsVersion": "2.6.17",
        "policyengineCoreVersion": "3.32.6", "assumeW2Wages": True, "disableSalt": False,
        "policyengineOutputDetail": 5,
    }
    (tmp_path / "provenance_2024.json").write_text(json.dumps(provenance))
    return population, source_sha, sha


def test_recorded_cli_maps_emulator_columns_and_scopes_tolerance(tmp_path):
    population, source_sha, sha = small_release(tmp_path)
    output = tmp_path / "report.json"
    result = CliRunner().invoke(cli, [
        "compare", "policyengine", "taxsim", "--population", "taxsim-csv",
        "--taxsim-csv", str(population), "--taxsim-csv-sha256", source_sha,
        "--period", "2024", "--sample-size", "0", "--report-suite", "replay-test",
        "--recorded-release", str(tmp_path), "--recorded-release-tag", "test-fixture",
        "--recorded-release-sha256", sha,
        "--concept", FEDERAL, "--concept", STATE,
        "--tolerance", "15", "--relative-tolerance", "0", "--row-aux-output", "niit",
        "--output", str(output),
    ])
    assert result.exit_code == 0, result.output
    report = json.loads(output.read_text())
    assert report["case_count"] == 2
    assert len(report["mismatches"]) == 3
    assert {row["concept"] for row in report["mismatches"]} == {FEDERAL, STATE}
    assert [row["case_id"] for row in report["mismatches"] if row["concept"] == STATE] == ["taxsim-2"]
    assert all(row["aux"] == {"left": {"niit": 12}, "right": {"niit": 12}}
               for row in report["mismatches"])
    assert report["engine_identity"]["taxsim"]["binaries"][0]["platform"] == "linux"
    assert report["engines"]["versions"]["policyengine_us"] == "2.6.17"
    assert report["recorded_release"]["sha256"] == sha


def test_recorded_cli_rejects_other_population(tmp_path):
    result = CliRunner().invoke(cli, ["compare", "policyengine", "taxsim", "--recorded-release", str(tmp_path)])
    assert result.exit_code != 0
    assert "requires population taxsim-csv" in result.output


def test_registry_replay_does_not_require_live_engine_packages(monkeypatch, tmp_path):
    module = registry()
    config = yaml.safe_load((ROOT / "comparisons/taxsim-emulator-ecps-2024.yaml").read_text())
    monkeypatch.setenv("AXIOM_TAXSIM_CSV", str(tmp_path / "inputs.csv"))
    monkeypatch.setenv("AXIOM_TAXSIM_RECORDED_RELEASE", str(tmp_path))
    commands = []
    monkeypatch.setattr(module.subprocess, "run", lambda cmd, **kwargs: commands.append(cmd))
    module._run_axiom_oracles_compare(config["runner"], tmp_path / "out.json")
    command = commands[0]
    assert command[0] == module.sys.executable
    assert "--with" not in command
    assert command[command.index("--relative-tolerance") + 1] == "0"
    assert command[command.index("--recorded-release-sha256") + 1].startswith("6e1692")


@pytest.mark.parametrize("year", range(2021, 2026))
def test_report_matches_vendored_dashboard_headlines(year):
    fixture = json.loads((ROOT / "tests/fixtures/taxsim_emulator_dashboard.json").read_text())
    expected = fixture["years"][str(year)]
    config = yaml.safe_load((ROOT / f"comparisons/taxsim-emulator-ecps-{year}.yaml").read_text())
    assert config["ci"] == "manual"
    assert "dashboard" not in config
    report = load_report(ROOT / config["artifacts"]["report_path"])
    assert report["case_count"] == expected["totalRecords"]
    aggregates = {item["concept"]: item for item in report["aggregates"]}
    for concept, headline in [(FEDERAL, "federalMatchPct"), (STATE, "stateMatchPct")]:
        aggregate = aggregates[concept]
        assert aggregate["comparison_count"] == expected["totalRecords"]
        assert round(aggregate["match_rate"], 1) == expected[headline]
        # Cross-check every persisted row, not just the headline summary.
        rows = [row for row in report["mismatches"] if row["concept"] == concept]
        assert len(rows) == aggregate["mismatch_count"]
        assert all(abs(row["difference"]) > 15 for row in rows)
        assert all({"v32", "v36", "niit", "addmed"} <= set(row["aux"]["left"]) for row in rows)
    assert len(report["mismatches"]) == sum(item["mismatch_count"] for item in aggregates.values())
    assert sum(item["rows"] for item in report["engine_identity"]["taxsim"]["binaries"]) == expected["totalRecords"]
    manifest = json.loads((ROOT / "dashboard/public/data/manifest.json").read_text())
    assert not any("taxsim-emulator" in name for name in manifest["reports"])
