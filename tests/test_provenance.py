"""Tests for the provenance module (O2) and run_comparison's stamping."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

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


def test_stamp_report_provenance_records_resolved_engine_versions(tmp_path):
    run_comparison = _load_run_comparison()
    report = tmp_path / "r.json"
    report.write_text(
        json.dumps(
            {
                "suite": "al-snap-ecps",
                "engines": {
                    "left": "axiom",
                    "right": "policyengine",
                    "versions": {
                        "policyengine": "4.18.9",
                        "policyengine_core": "3.30.3",
                        "policyengine_us": "1.767.3",
                    },
                },
            }
        )
    )
    block = {
        "engine": {"axiom_rules_engine_version": "0.1.0"},
        "oracle": {
            "policyengine_package": "policyengine==4.18.9",
            "policyengine_us": "1.767.3",
            "policyengine_core": "3.30.3",
        },
    }

    run_comparison._stamp_report_provenance(
        report, block, require_engine_versions=True
    )

    written = json.loads(report.read_text())
    assert written["engines"]["versions"] == {
        "axiom_rules_engine": "0.1.0",
        "policyengine": "4.18.9",
        "policyengine_core": "3.30.3",
        "policyengine_us": "1.767.3",
    }


def test_stamp_report_provenance_rejects_runtime_engine_mismatch(tmp_path):
    run_comparison = _load_run_comparison()
    report = tmp_path / "r.json"
    report.write_text(
        json.dumps(
            {
                "engines": {
                    "left": "axiom",
                    "right": "policyengine",
                    "versions": {
                        "policyengine": "4.18.9",
                        "policyengine_core": "3.28.0",
                        "policyengine_us": "1.767.3",
                    },
                }
            }
        )
    )
    block = {
        "oracle": {
            "policyengine_package": "policyengine==4.18.9",
            "policyengine_us": "1.767.3",
            "policyengine_core": "3.30.3",
        }
    }

    with pytest.raises(SystemExit, match="runtime engine versions"):
        run_comparison._stamp_report_provenance(
            report, block, require_engine_versions=True
        )


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
    # Hermetic: ssi-ecps is a real mapped suite, so the affected-map completion
    # would otherwise fill the sha from this machine's supervised checkout —
    # this test pins the declared-roots threading, so nothing may resolve.
    import axiom_oracles.provenance as provenance

    monkeypatch.setattr(provenance, "resolve_rulespec_checkout", lambda slug: None)
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
    assert block["oracle"]["policyengine_core"] == "3.28.0"
    assert block["rulespecs"] == [
        {"repo": "TheAxiomFoundation/rulespec-us", "sha": None}
    ]
    # dataset falls back to the config population when no identity is present.
    assert block["dataset"]["population"] == "enhanced-cps"


def test_state_income_tax_provenance_uses_suite_local_oracle_pins(tmp_path):
    run_comparison = _load_run_comparison()
    output = tmp_path / "ri.json"
    output.write_text(json.dumps({"suite": "ri-income-tax-liability"}))
    config = {
        "name": "ri-income-tax-liability",
        "runner": {
            "type": "state-income-tax-liability-grid",
            "parameters": {
                "state": "RI",
                "policyengine_version": "4.18.9",
                "policyengine_us_version": "1.784.4",
                "policyengine_core_version": "3.30.3",
            },
        },
    }

    block = run_comparison._build_run_provenance(
        config,
        "state-income-tax-liability-grid",
        output,
    )

    assert block["oracle"] == {
        "name": "policyengine-taxsim",
        "policyengine_package": "policyengine==4.18.9",
        "policyengine_us": "1.784.4",
        "policyengine_core": "3.30.3",
        "policyengine_taxsim": "2.30.0",
    }


def test_direct_de_oracle_provenance_has_both_engines_and_no_rulespecs(
    tmp_path, monkeypatch
):
    run_comparison = _load_run_comparison()
    model_root = tmp_path / "EUROMOD_RELEASES_J2.0+"
    model_root.mkdir()
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "de-worker-dual-oracle"}))
    config = {
        "name": "de-worker-dual-oracle",
        "runner": {
            "type": "gettsim-synthetic-compare",
            "parameters": {
                "population": "synthetic",
                "euromod_model_root": str(model_root),
                "euromod_country": "DE",
                "euromod_system": "DE_2025",
                "euromod_dataset": "DE_2024_b1_2015_03_e2",
                "gettsim_version": "1.2.1",
                "gettsim_policy_date": "2025-06-30",
            },
        },
    }

    block = run_comparison._build_run_provenance(
        config, "gettsim-synthetic-compare", output
    )

    assert block.get("rulespecs", []) == []
    assert block.get("engine", {}) == {}
    assert block["oracle"] == {
        "name": "euromod-gettsim",
        "euromod_release": "J2.0+",
        "euromod_country": "DE",
        "euromod_system": "DE_2025",
        "euromod_dataset": "DE_2024_b1_2015_03_e2",
        "gettsim_version": "1.2.1",
        "gettsim_policy_date": "2025-06-30",
    }


def test_resolve_rulespec_checkout_prefers_git_bearing_candidates(
    monkeypatch, tmp_path
):
    """The resolver walks the supervised-layout conventions and prefers the
    first candidate that can actually prove a SHA — an rsync'd root without
    .git is a last resort, never a silent winner over a real checkout."""
    from axiom_oracles import provenance

    home = tmp_path
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    rsync_copy = home / ".axiom-oracles" / "roots" / "rulespec-us"
    rsync_copy.mkdir(parents=True)
    org_checkout = home / "TheAxiomFoundation" / "rulespec-us"
    org_checkout.mkdir(parents=True)

    monkeypatch.setattr(
        provenance,
        "_git_sha",
        lambda path: "e" * 40 if path == org_checkout else None,
    )
    assert provenance.resolve_rulespec_checkout(
        "TheAxiomFoundation/rulespec-us"
    ) == org_checkout

    # Without any git-bearing candidate the first existing path still returns
    # (its SHA will be None — the selector's conservative reading survives).
    monkeypatch.setattr(provenance, "_git_sha", lambda path: None)
    assert provenance.resolve_rulespec_checkout(
        "TheAxiomFoundation/rulespec-us"
    ) == org_checkout

    assert provenance.resolve_rulespec_checkout("TheAxiomFoundation/rulespec-nz") is None


def test_resolve_rulespec_checkout_walks_uk_official_alias(monkeypatch, tmp_path):
    from axiom_oracles import provenance

    home = tmp_path
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    official = home / "rulespec-uk-official"
    official.mkdir(parents=True)
    monkeypatch.setattr(provenance, "_git_sha", lambda path: "f" * 40)
    assert provenance.resolve_rulespec_checkout(
        "TheAxiomFoundation/rulespec-uk"
    ) == official


def test_snap_qc_skip_reemit_never_resolves_recorded_root(tmp_path, monkeypatch):
    """NEGATIVE (cross-family review): a snap-qc skip re-emits the committed
    report; with the CI materializer cloning the recorded rulespec_root path
    fresh at main HEAD, resolving that path would stamp the re-emitted numbers
    as fresh. The re-emit marker must suppress the path resolution (#296)."""
    run_comparison = _load_run_comparison()
    checkout = tmp_path / "rulespec-us"
    checkout.mkdir()
    output = tmp_path / "r.json"
    output.write_text(
        json.dumps(
            {
                "suite": "az-snap-qc",
                "summary": {"provenance": {"rulespec_root": str(checkout)}},
            }
        )
    )
    config = {
        "name": "az-snap-qc",
        "runner": {
            "type": "snap-qc-compare",
            "_reemitted_report": True,
            "parameters": {"jurisdiction": "us-az", "fiscal_year": 2024},
        },
    }
    block = run_comparison._build_run_provenance(config, "snap-qc-compare", output)
    assert "rulespecs" not in block

    # A real (non-re-emitted) run keeps the recorded-root resolution.
    config["runner"].pop("_reemitted_report")
    block = run_comparison._build_run_provenance(config, "snap-qc-compare", output)
    assert block.get("rulespecs"), "real runs still record the root they used"


def test_reemit_strips_shas_from_explicitly_configured_roots(tmp_path):
    """NEGATIVE (cross-family review round 2): a suite that CONFIGURES
    rulespec_root(s) bypasses the recorded-root special case — the general
    path collection would still resolve the checkout's current SHA on a skip.
    The re-emit flag must strip SHAs from every rulespec entry, whatever path
    produced it (#296)."""
    run_comparison = _load_run_comparison()
    checkout = tmp_path / "rulespec-us"
    checkout.mkdir()
    import subprocess as sp

    sp.run(["git", "init", "-q", str(checkout)], check=True)
    sp.run(["git", "-C", str(checkout), "commit", "-q", "--allow-empty",
            "-m", "x"], check=True,
           env={**__import__("os").environ,
                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "az-snap-qc"}))
    config = {
        "name": "az-snap-qc",
        "runner": {
            "type": "snap-qc-compare",
            "_reemitted_report": True,
            "rulespec_root": str(checkout),
            "parameters": {"jurisdiction": "us-az", "fiscal_year": 2024},
        },
    }
    block = run_comparison._build_run_provenance(config, "snap-qc-compare", output)
    for entry in block.get("rulespecs", []):
        assert entry.get("sha") is None, entry
