"""Tests for the provenance module (O2) and run_comparison's stamping."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

from axiom_oracles.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    RUN_KINDS,
    build_provenance,
    dataset_provenance_from_identity,
    engine_provenance,
    repo_slug_from_remote,
    resolve_run_kind,
    rulespec_provenance,
)


def _load_run_comparison():
    module_path = Path(__file__).parents[1] / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("run_comparison", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --- build_provenance -------------------------------------------------------


def test_build_provenance_always_has_schema_and_timestamp():
    block = build_provenance(generated_by="x")
    assert block["schema"] == PROVENANCE_SCHEMA_VERSION
    assert block["generated_at"].endswith("Z")
    assert block["run_kind"] in RUN_KINDS


def test_build_provenance_omits_empty_subblocks():
    block = build_provenance(generated_by="x", rulespecs=[], engine={}, dataset=None)
    assert "rulespecs" not in block
    assert "engine" not in block
    assert "dataset" not in block


def test_build_provenance_drops_none_valued_fields_inside_subblocks():
    block = build_provenance(
        generated_by="x",
        oracle={"name": "policyengine", "policyengine_us": None},
    )
    assert block["oracle"] == {"name": "policyengine"}


def test_resolve_run_kind_env(monkeypatch):
    monkeypatch.setenv("AXIOM_ORACLES_RUN_KIND", "weekly")
    assert resolve_run_kind() == "weekly"
    monkeypatch.setenv("AXIOM_ORACLES_RUN_KIND", "not-a-kind")
    # NEGATIVE: an invalid run kind is rejected, falling back to the default.
    assert resolve_run_kind() == "manual"


# --- repo slug + rulespec provenance ---------------------------------------


def test_repo_slug_from_remote_forms():
    assert (
        repo_slug_from_remote("git@github.com:TheAxiomFoundation/rulespec-us.git")
        == "TheAxiomFoundation/rulespec-us"
    )
    assert (
        repo_slug_from_remote("https://github.com/TheAxiomFoundation/rulespec-us")
        == "TheAxiomFoundation/rulespec-us"
    )
    # NEGATIVE: a non-GitHub remote yields no slug rather than a wrong one.
    assert repo_slug_from_remote("file:///tmp/rulespec-us") is None
    assert repo_slug_from_remote(None) is None


def test_rulespec_provenance_uses_git_when_available(tmp_path):
    repo = tmp_path / "rulespec-us"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)

    entries = rulespec_provenance([repo])
    assert len(entries) == 1
    # No remote → canonical <owner>/<basename>, matching the affected-map keys.
    assert entries[0]["repo"] == "TheAxiomFoundation/rulespec-us"
    assert entries[0]["sha"] and len(entries[0]["sha"]) == 40


def test_rulespec_provenance_missing_path_records_name_with_null_sha(tmp_path):
    entries = rulespec_provenance([tmp_path / "rulespec-us-co"])
    assert entries == [{"repo": "TheAxiomFoundation/rulespec-us-co", "sha": None}]


def test_rulespec_provenance_canonicalizes_uk_official_alias(tmp_path):
    entries = rulespec_provenance([tmp_path / "rulespec-uk-official"])
    assert entries == [{"repo": "TheAxiomFoundation/rulespec-uk", "sha": None}]


def test_rulespec_provenance_dedupes(tmp_path):
    missing = tmp_path / "rulespec-us"
    entries = rulespec_provenance([missing, missing])
    assert entries == [{"repo": "TheAxiomFoundation/rulespec-us", "sha": None}]


def test_engine_provenance_reads_cargo_version(tmp_path):
    repo = tmp_path / "axiom-rules"
    repo.mkdir()
    (repo / "Cargo.toml").write_text(
        '[package]\nname = "axiom-rules-engine"\nversion = "0.4.2"\n'
    )
    prov = engine_provenance(repo)
    assert prov["axiom_rules_engine_version"] == "0.4.2"


def test_engine_provenance_none_repo():
    prov = engine_provenance(None)
    assert prov["axiom_rules_engine_sha"] is None


# --- dataset identity reuse -------------------------------------------------


def test_dataset_provenance_from_identity_keeps_pin_fields():
    identity = {
        "source": "populace-hf",
        "repo_id": "policyengine/populace-us",
        "revision": "rev",
        "sha256": "deadbeef",
        "built_with": "1.729.0",
        "irrelevant": "drop-me",
    }
    out = dataset_provenance_from_identity(identity)
    assert out["repo_id"] == "policyengine/populace-us"
    assert "irrelevant" not in out


def test_dataset_provenance_from_identity_none():
    assert dataset_provenance_from_identity(None) is None
    assert dataset_provenance_from_identity({}) is None


# --- run_comparison stamping ------------------------------------------------


def test_stamp_report_provenance_writes_block(tmp_path):
    run_comparison = _load_run_comparison()
    report = tmp_path / "r.json"
    report.write_text(json.dumps({"suite": "x", "aggregates": []}))
    block = {"schema": PROVENANCE_SCHEMA_VERSION, "run_kind": "manual"}
    run_comparison._stamp_report_provenance(report, block)
    written = json.loads(report.read_text())
    assert written["provenance"] == block


def test_stamp_preserves_sorted_format_and_newline(tmp_path):
    """A dashboard-style sorted+newline report stays sorted with its newline."""
    run_comparison = _load_run_comparison()
    report = tmp_path / "r.json"
    report.write_text(
        json.dumps({"suite": "x", "aggregates": []}, indent=2, sort_keys=True) + "\n"
    )
    run_comparison._stamp_report_provenance(report, {"schema": "v1"})
    text = report.read_text()
    assert text.endswith("\n")
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def test_stamp_preserves_insertion_order(tmp_path):
    """NEGATIVE (regression): stamping must NOT alphabetically reorder keys of a
    report the runner wrote in insertion order."""
    run_comparison = _load_run_comparison()
    report = tmp_path / "r.json"
    report.write_text(json.dumps({"zzz": 1, "suite": "x", "aaa": 2}, indent=2))
    run_comparison._stamp_report_provenance(report, {"schema": "v1"})
    text = report.read_text()
    assert not text.endswith("\n")  # original had none
    assert text.index("zzz") < text.index("aaa")  # order preserved


def test_build_run_provenance_threads_rulespecs_and_oracle(tmp_path, monkeypatch):
    run_comparison = _load_run_comparison()
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "ssi-ecps"}))
    config = {
        "name": "ssi-ecps",
        "runner": {
            "type": "axiom-oracles-compare",
            "axiom_rules_repo": str(tmp_path / "missing-rules"),
            "parameters": {
                "left": "axiom",
                "right": "policyengine",
                "population": "enhanced-cps",
                "rulespec_roots": [str(tmp_path / "rulespec-us")],
            },
        },
    }
    block = run_comparison._build_run_provenance(config, "axiom-oracles-compare", output)
    assert block["schema"] == PROVENANCE_SCHEMA_VERSION
    assert block["oracle"]["name"] == "policyengine"
    assert block["rulespecs"] == [
        {"repo": "TheAxiomFoundation/rulespec-us", "sha": None}
    ]
    # dataset falls back to the config population when no identity is present.
    assert block["dataset"]["population"] == "enhanced-cps"
