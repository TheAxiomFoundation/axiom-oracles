"""Metadata-only refresh preserves calculations and rejects unbound sources."""

import copy
import gc
import hashlib
import json

import pytest
import yaml

from axiom_oracles.adapters.taxsim.pins import resolve_binary
from axiom_oracles.comparison.report_io import load_report, write_report
from axiom_oracles.populations.taxsim_csv import read_taxsim_csv
from scripts import refresh_taxsim_emulator_metadata as refresh


@pytest.fixture
def example(tmp_path):
    source = tmp_path / "inputs.csv"
    source.write_text("taxsimid,year,state,mstat,page,scorp\n1,2021,1,1,40,25\n2,2021,21,1,45,0\n")
    population = read_taxsim_csv(source, period=2024)
    selection = population.select(scope=refresh.SCOPE, sample_size=0)
    identity = {**population.identity, "selection": selection.summary}
    concepts = ["us:tax/federal-income-tax#liability", "us:tax/state-income-tax#liability"]
    raw_output = b"immutable paired release output\n"
    output_sha = hashlib.sha256(raw_output).hexdigest()
    release_provenance = {
        "year": 2024, "records": 2, "sourceSha256": identity["sha256"],
        "outputSha256": output_sha,
    }
    provenance_bytes = json.dumps(release_provenance).encode()
    recorded = {
        "repo": "PolicyEngine/policyengine-taxsim", "tag": "pinned-release",
        "sha256": output_sha, "file": "comparison_results_2024.csv",
        "provenance_file": "provenance_2024.json", "provenance": release_provenance,
        "provenance_sha256": hashlib.sha256(provenance_bytes).hexdigest(),
    }
    binaries = [{"sha256": resolve_binary(state, 2024, "linux", "dashboard-2026-09"),
                 "rows": 1, "platform": "linux"} for state in (1, 21)]
    config = {
        "name": "taxsim-emulator-ecps-2024",
        "runner": {"type": "axiom-oracles-compare", "parameters": {
            "period": "2024", "population": "taxsim-csv", "left": "policyengine",
            "right": "taxsim", "sample_size": 0, "report_include_cases": False,
            "tolerance": 15, "relative_tolerance": 0, "concepts": concepts,
            "taxsim_csv": {"sha256": identity["sha256"], "selector_fact_columns": ["scorp"]},
            "taxsim_pin_profile": "dashboard-2026-09",
            "recorded_release": {"repo": recorded["repo"], "tag": recorded["tag"],
                                 "sha256_by_year": {"2024": output_sha}},
        }},
        "artifacts": {"report_path": "reports/taxsim-emulator/taxsim-emulator-ecps-2024.json.gz"},
    }
    report = {
        "suite": config["name"], "population": "taxsim-csv", "scope": refresh.SCOPE,
        "engines": {"left": "policyengine", "right": "taxsim"}, "case_count": 2,
        "case_rows_omitted": True,
        "concepts": [{"id": c, "tolerance": 15, "relative_tolerance": 0} for c in concepts],
        "summary": {"comparison_count": 4, "match_count": 2, "mismatch_count": 2},
        "aggregates": [{"left_weighted_sum": 10.25, "right_weighted_sum": 205}],
        "dataset_identity": identity, "recorded_release": recorded,
        "engine_identity": {"taxsim": {"pin_profile": "dashboard-2026-09", "binaries": binaries}},
        "provenance": {
            "generated_at": "2026-09-24T01:00:00Z", "dataset": copy.deepcopy(identity),
            "oracle": {"recorded_release": copy.deepcopy(recorded), "taxsim_binaries": binaries,
                       "taxsim_pin_profile": "dashboard-2026-09"},
        },
        "mismatches": [{
            "case_id": case.case_id, "concept": concepts[1], "kind": "amount_difference",
            "left": 10.25, "right": 100, "difference": -89.75,
            "aux": {"left": {"niit": 1}, "right": {"niit": 2}},
            "facts": dict(case.metadata["selector_facts"]),
        } for case in selection.cases],
    }
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    (release_dir / recorded["file"]).write_bytes(raw_output)
    (release_dir / recorded["provenance_file"]).write_bytes(provenance_bytes)
    return report, config, source, release_dir


def _without_refreshed_metadata(report):
    result = copy.deepcopy(report)
    for row in result["mismatches"]:
        row.pop("facts")
        row.pop("taxsim_binary_sha256", None)
    result["dataset_identity"].pop("selection")
    result["provenance"]["dataset"].pop("selection")
    return result


def test_refresh_preserves_all_outputs_and_is_idempotent(example):
    report, config, source, release_dir = example
    before = _without_refreshed_metadata(report)
    assert refresh.refresh_metadata(report, config, source, release_dir=release_dir)
    assert _without_refreshed_metadata(report) == before
    assert [row["facts"]["scorp"] for row in report["mismatches"]] == [25, 0]
    assert [row["taxsim_binary_sha256"] for row in report["mismatches"]] == [
        resolve_binary(state, 2024, "linux", "dashboard-2026-09") for state in (1, 21)
    ]
    assert report["dataset_identity"]["selection"]["selector_fact_columns"] == ["scorp"]
    assert report["dataset_identity"] == report["provenance"]["dataset"]
    assert not refresh.refresh_metadata(report, config, source, release_dir=release_dir)


@pytest.mark.parametrize("corruption", [
    "source", "report_source", "missing_id", "state", "year", "foreign_sha",
    "profile", "missing_binary", "release_repo", "release_sha", "provenance_output",
    "provenance_source", "comparison_count", "duplicate_row", "raw_csv", "raw_provenance",
])
def test_refresh_fails_before_mutation_on_wrong_identity(example, corruption):
    report, config, source, release_dir = example
    if corruption == "source":
        source.write_text(source.read_text().replace(",25", ",26"))
    elif corruption == "report_source":
        report["dataset_identity"]["sha256"] = "a" * 64
    elif corruption == "missing_id":
        report["mismatches"][0]["case_id"] = "taxsim-999"
    elif corruption in {"state", "year"}:
        report["mismatches"][0]["facts"][corruption] = "wrong"
    elif corruption == "foreign_sha":
        report["mismatches"][0]["taxsim_binary_sha256"] = "f" * 64
    elif corruption == "profile":
        report["engine_identity"]["taxsim"]["pin_profile"] = "other"
    elif corruption == "missing_binary":
        report["engine_identity"]["taxsim"]["binaries"].pop()
    elif corruption == "release_repo":
        report["recorded_release"]["repo"] = "foreign/repo"
    elif corruption == "release_sha":
        config["runner"]["parameters"]["recorded_release"]["sha256_by_year"]["2024"] = "a" * 64
    elif corruption.startswith("provenance_"):
        field = "outputSha256" if corruption.endswith("output") else "sourceSha256"
        report["recorded_release"]["provenance"][field] = "a" * 64
        report["provenance"]["oracle"]["recorded_release"]["provenance"][field] = "a" * 64
    elif corruption == "comparison_count":
        report["summary"]["comparison_count"] += 1
    elif corruption == "duplicate_row":
        report["mismatches"][1] = copy.deepcopy(report["mismatches"][0])
    elif corruption == "raw_csv":
        (release_dir / "comparison_results_2024.csv").write_text("wrong outputs")
    elif corruption == "raw_provenance":
        (release_dir / "provenance_2024.json").write_text("{}")
    before = copy.deepcopy(report)
    with pytest.raises(ValueError):
        refresh.refresh_metadata(report, config, source, release_dir=release_dir)
    assert report == before


def test_cli_check_never_writes_and_refresh_uses_deterministic_gzip(example, tmp_path, monkeypatch):
    report, config, source, release_dir = example
    monkeypatch.setattr(refresh, "REPO_ROOT", tmp_path)
    (tmp_path / "comparisons").mkdir()
    (tmp_path / "comparisons/taxsim-emulator-ecps-2024.yaml").write_text(yaml.safe_dump(config))
    path = tmp_path / config["artifacts"]["report_path"]
    write_report(path, report)
    original = path.read_bytes()
    args = ["--taxsim-csv", str(source), "--release-dir", str(release_dir), "--year", "2024"]
    assert refresh.main([*args, "--check"]) == 1
    assert path.read_bytes() == original
    assert refresh.main(args) == 0
    rewritten = path.read_bytes()
    assert rewritten[4:8] == b"\x00" * 4
    assert load_report(path)["mismatches"][0]["facts"]["scorp"] == 25
    assert refresh.main([*args, "--check"]) == 0
    assert refresh.main(args) == 0
    assert path.read_bytes() == rewritten


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("fail", [False, True])
def test_file_refresh_restores_gc_state_on_success_and_error(example, monkeypatch, enabled, fail):
    report, config, source, release_dir = example

    def load(_path):
        assert not gc.isenabled()
        if fail:
            raise ValueError("invalid report")
        return report

    monkeypatch.setattr(refresh, "load_report", load)
    original = gc.isenabled()
    (gc.enable if enabled else gc.disable)()
    try:
        if fail:
            with pytest.raises(ValueError, match="invalid report"):
                refresh._refresh_report_file(source, config, source, release_dir=release_dir, check=True)
        else:
            assert refresh._refresh_report_file(source, config, source, release_dir=release_dir, check=True)
        assert gc.isenabled() is enabled
    finally:
        (gc.enable if original else gc.disable)()
