"""Tests for the provenance module (O2) and run_comparison's stamping."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from axiom_oracles.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    RUN_KINDS,
    build_provenance,
    dataset_provenance_from_identity,
    engine_provenance,
    is_real_run_report,
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


# --- is_real_run_report ------------------------------------------------------


@pytest.mark.parametrize(
    ("report", "real"),
    [
        ({"provenance": {"run_kind": "manual", "rulespecs": []}}, True),
        ({"provenance": {"reemitted_report": False}}, True),
        ({"suite": "unstamped-legacy"}, True),
        ({"provenance": None}, True),
        ({"provenance": {"reemitted_report": True}}, False),
        (None, False),
        ([{"provenance": {}}], False),
        ("report", False),
    ],
)
def test_is_real_run_report(report, real):
    """A re-emission is exactly a report marked reemitted_report; anything
    else shaped like a report counts as a real (possibly legacy) run."""
    assert is_real_run_report(report) is real


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
    entries = rulespec_provenance([tmp_path / "rulespec-uk"])
    assert entries == [{"repo": "TheAxiomFoundation/rulespec-uk", "sha": None}]


@pytest.mark.parametrize("exists", [True, False])
def test_rulespec_provenance_folds_an_absorbed_basename(tmp_path, exists):
    """A directory named for an absorbed state repo (an rsync of the monorepo's
    us-co/, with no .git), present or not, is keyed under rulespec-us, the repo
    whose rules it copies, so the stamp and the affected map name the same
    repo."""
    root = tmp_path / "rulespec-us-co"
    if exists:
        root.mkdir()
    entries = rulespec_provenance([root])
    assert entries == [{"repo": "TheAxiomFoundation/rulespec-us", "sha": None}]


def test_rulespec_provenance_stamps_an_archived_clone_under_its_true_name(tmp_path):
    """NEGATIVE: a git checkout whose remote is an archived state repo is
    stamped under that name, never folded. A run that really read frozen
    archived rules must not look like it ran against rulespec-us (the
    end-to-end rerun through provenance completion and the selector is
    tests/test_run_comparison.py
    test_archived_clone_run_is_never_stamped_fresh)."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "remote", "add", "origin",
            "https://github.com/TheAxiomFoundation/rulespec-us-co.git",
        ],
        check=True,
    )
    (repo / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)

    [entry] = rulespec_provenance([repo])
    assert entry["repo"] == "TheAxiomFoundation/rulespec-us-co"
    assert entry["sha"] and len(entry["sha"]) == 40


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("rulespec-us-co", "TheAxiomFoundation/rulespec-us"),
        ("rulespec-us-dc", "TheAxiomFoundation/rulespec-us"),
        ("rulespec-us-ak", "TheAxiomFoundation/rulespec-us"),  # never existed
        ("TheAxiomFoundation/rulespec-us-tx", "TheAxiomFoundation/rulespec-us"),
        ("theaxiomfoundation/rulespec-us-co", "TheAxiomFoundation/rulespec-us"),
        ("TheAxiomFoundation/RuleSpec-US-CO", "TheAxiomFoundation/rulespec-us"),
        ("THEAXIOMFOUNDATION/RULESPEC-US-CO", "TheAxiomFoundation/rulespec-us"),
        (
            "theaxiomfoundation/RuleSpec-UK-Kingston-Upon-Thames",
            "TheAxiomFoundation/rulespec-uk",
        ),
        (
            "rulespec-uk-kingston-upon-thames",
            "TheAxiomFoundation/rulespec-uk",
        ),
        ("rulespec-us", "TheAxiomFoundation/rulespec-us"),
        ("rulespec-uk-official", "TheAxiomFoundation/rulespec-uk"),
        # Not absorbed: left alone, never collapsed by a hyphen rule.
        ("rulespec-us-32d", "TheAxiomFoundation/rulespec-us-32d"),
        ("rulespec-graph-viewer", "TheAxiomFoundation/rulespec-graph-viewer"),
        ("rulespec-tz-znz", "TheAxiomFoundation/rulespec-tz-znz"),
        ("rulespec-nz-pr70", "TheAxiomFoundation/rulespec-nz-pr70"),
        # Another owner's repo of the same name is not ours to fold.
        ("someone/rulespec-us-co", "someone/rulespec-us-co"),
        ("axiom-compose", "axiom-compose"),
    ],
)
def test_canonical_rulespec_slug_folds_absorbed_repos(name, expected):
    from axiom_oracles.provenance import canonical_rulespec_slug

    assert canonical_rulespec_slug(name) == expected


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


def _git_checkout(path, message):
    path.mkdir(parents=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.test",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.test",
    }
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "--allow-empty", "-m", message],
        check=True,
        env=env,
    )
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _pinned_roots_config(roots):
    # co-tax-intersection-taxsim is a real affected-map suite mapped to
    # rulespec-us that pins its snapshot through axiom_rulespec_repo_roots.
    return {
        "name": "co-tax-intersection-taxsim",
        "dashboard": {"suite": "co-tax-intersection-taxsim"},
        "runner": {
            "type": "axiom-oracles-compare",
            "parameters": {
                "left": "axiom",
                "right": "taxsim",
                "axiom_rulespec_repo_roots": str(roots),
            },
        },
    }


def test_pinned_repo_roots_win_over_the_convention_checkout(tmp_path, monkeypatch):
    """A suite that compiles against ``axiom_rulespec_repo_roots`` must be
    stamped with the checkout under those roots, not the developer's
    ``~/TheAxiomFoundation/rulespec-us`` (which the affected-map completion
    would otherwise resolve)."""
    run_comparison = _load_run_comparison()
    import axiom_oracles.provenance as provenance

    pinned_sha = _git_checkout(tmp_path / "oracle-pins" / "rulespec-us", "pin")
    convention = tmp_path / "convention" / "rulespec-us"
    _git_checkout(convention, "moving main")
    monkeypatch.setattr(provenance, "resolve_rulespec_checkout", lambda slug: convention)
    monkeypatch.delenv("AXIOM_RULESPEC_US_ROOT", raising=False)
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "co-tax-intersection-taxsim"}))

    block = run_comparison._build_run_provenance(
        _pinned_roots_config(tmp_path / "oracle-pins"), "axiom-oracles-compare", output
    )

    assert block["rulespecs"] == [
        {"repo": "TheAxiomFoundation/rulespec-us", "sha": pinned_sha}
    ]


def test_pinned_repo_roots_honor_the_rulespec_us_override(tmp_path, monkeypatch):
    """AXIOM_RULESPEC_US_ROOT's parent is prepended to the exported roots, so
    the run resolves rulespec-us there; provenance must follow it."""
    run_comparison = _load_run_comparison()
    import axiom_oracles.provenance as provenance

    _git_checkout(tmp_path / "oracle-pins" / "rulespec-us", "pin")
    # The engine reaches the override only as <parent>/rulespec-us (the
    # override's parent is prepended to the exported roots), so an override
    # directory with another name is NOT what compiles.
    _git_checkout(tmp_path / "snapshot" / "rulespec-us-worktree", "override dir")
    override_sha = _git_checkout(tmp_path / "snapshot" / "rulespec-us", "sibling")
    monkeypatch.setattr(provenance, "resolve_rulespec_checkout", lambda slug: None)
    monkeypatch.setenv(
        "AXIOM_RULESPEC_US_ROOT", str(tmp_path / "snapshot" / "rulespec-us-worktree")
    )
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "co-tax-intersection-taxsim"}))

    block = run_comparison._build_run_provenance(
        _pinned_roots_config(tmp_path / "oracle-pins"), "axiom-oracles-compare", output
    )

    assert block["rulespecs"] == [
        {"repo": "TheAxiomFoundation/rulespec-us", "sha": override_sha}
    ]


def test_a_root_naming_a_rulespec_checkout_is_lifted_to_its_parent(
    tmp_path, monkeypatch
):
    """The engine treats a root that is itself a rulespec-* checkout as its
    parent (``_default_rulespec_repo_roots``); provenance must too."""
    run_comparison = _load_run_comparison()
    import axiom_oracles.provenance as provenance

    pinned_sha = _git_checkout(tmp_path / "pins" / "rulespec-us", "pin")
    monkeypatch.setattr(provenance, "resolve_rulespec_checkout", lambda slug: None)
    monkeypatch.delenv("AXIOM_RULESPEC_US_ROOT", raising=False)
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "co-tax-intersection-taxsim"}))

    block = run_comparison._build_run_provenance(
        _pinned_roots_config(tmp_path / "pins" / "rulespec-us"),
        "axiom-oracles-compare",
        output,
    )

    assert block["rulespecs"] == [
        {"repo": "TheAxiomFoundation/rulespec-us", "sha": pinned_sha}
    ]


def test_absent_pinned_roots_fall_back_to_the_convention_checkout(
    tmp_path, monkeypatch
):
    run_comparison = _load_run_comparison()
    import axiom_oracles.provenance as provenance

    convention = tmp_path / "convention" / "rulespec-us"
    convention_sha = _git_checkout(convention, "main")
    monkeypatch.setattr(provenance, "resolve_rulespec_checkout", lambda slug: convention)
    monkeypatch.delenv("AXIOM_RULESPEC_US_ROOT", raising=False)
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "co-tax-intersection-taxsim"}))

    block = run_comparison._build_run_provenance(
        _pinned_roots_config(tmp_path / "missing-roots"), "axiom-oracles-compare", output
    )

    assert block["rulespecs"] == [
        {"repo": "TheAxiomFoundation/rulespec-us", "sha": convention_sha}
    ]


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


def test_resolve_rulespec_checkout_never_lands_on_an_archived_clone(
    monkeypatch, tmp_path
):
    """NEGATIVE: supervised machines keep archived rulespec-us-<st> clones
    under ~/TheAxiomFoundation. A rulespec-us lookup must not return one, and
    a lookup by an absorbed name resolves the monorepo that holds its rules,
    so provenance completion can only stamp a SHA of rulespec-us."""
    from axiom_oracles import provenance

    home = tmp_path
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("AXIOM_RULESPEC_US_ROOT", raising=False)
    archived = home / "TheAxiomFoundation" / "rulespec-us-co"
    archived.mkdir(parents=True)
    (home / ".axiom-oracles" / "roots" / "rulespec-us-co").mkdir(parents=True)
    monkeypatch.setattr(provenance, "_git_sha", lambda path: "a" * 40)

    assert provenance.resolve_rulespec_checkout("TheAxiomFoundation/rulespec-us") is None
    assert provenance.resolve_rulespec_checkout("TheAxiomFoundation/rulespec-us-co") is None

    monorepo = home / "TheAxiomFoundation" / "rulespec-us"
    monorepo.mkdir()
    for slug in ("TheAxiomFoundation/rulespec-us", "TheAxiomFoundation/rulespec-us-co"):
        assert provenance.resolve_rulespec_checkout(slug) == monorepo


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


@pytest.mark.parametrize("location", ["override", "convention"])
@pytest.mark.parametrize(
    "remote_slug",
    ["theaxiomfoundation/RuleSpec-US-CO", "someone/rulespec-us"],
)
def test_resolve_rulespec_checkout_rejects_a_renamed_wrong_repository(
    location, remote_slug, monkeypatch, tmp_path
):
    """A country-named directory cannot establish country provenance when
    its GitHub origin identifies an absorbed state or another owner's repo.
    An invalid pinned root must not substitute a convention checkout's SHA.
    """
    from axiom_oracles import provenance

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("AXIOM_RULESPEC_US_ROOT", raising=False)
    convention = tmp_path / "TheAxiomFoundation" / "rulespec-us"
    candidate = tmp_path / "renamed" / "rulespec-us" if location == "override" else convention
    candidate.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(candidate)], check=True)
    subprocess.run(
        ["git", "-C", str(candidate), "remote", "add", "origin",
         f"https://github.com/{remote_slug}.git"],
        check=True,
    )
    monkeypatch.setattr(provenance, "_git_sha", lambda path: "a" * 40)
    if location == "override":
        monkeypatch.setenv("AXIOM_RULESPEC_US_ROOT", str(candidate))
        convention.mkdir(parents=True)

    country = "TheAxiomFoundation/rulespec-us"
    assert provenance.resolve_rulespec_checkout(country) is None
    output = tmp_path / "output.json"
    output.write_text("{}")
    rc = _load_run_comparison()
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    (comparisons / "affected_map.json").write_text(json.dumps({
        "suites": [{"suite": "demo", "name": "demo", "repos": [country]}]
    }))
    monkeypatch.setattr(rc, "COMPARISONS_DIR", comparisons)
    block = rc._build_run_provenance(
        {"name": "demo", "runner": {}}, "axiom-encode-snap-ecps-compare", output
    )
    assert block["rulespecs"] == [{"repo": country, "sha": None}]


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


def test_reemit_records_no_engine_and_keeps_the_copied_engine_label(
    tmp_path, monkeypatch
):
    """A re-emission executed no engine, so it must not claim the leg's own
    checkout. Recording it relabeled copied numbers: re-emissions of the BE
    marital-quotient report turned its real run's axiom_rules_engine 0.1.0
    into 0.2.2 in the report body (engines.versions)."""
    run_comparison = _load_run_comparison()
    import axiom_oracles.provenance as provenance_module

    monkeypatch.setattr(
        provenance_module,
        "engine_provenance",
        lambda _repo: {
            "axiom_rules_engine_sha": "e" * 40,
            "axiom_rules_engine_version": "0.2.2",
        },
    )
    output = tmp_path / "r.json"
    copied = {
        "suite": "be-marital-quotient",
        "engines": {
            "left": "euromod",
            "right": "axiom",
            "versions": {"axiom_rules_engine": "0.1.0"},
        },
    }
    output.write_text(json.dumps(copied, indent=2, sort_keys=True))
    config = {
        "name": "be-marital-quotient",
        "runner": {
            "type": "euromod-synthetic-compare",
            "_reemitted_report": True,
            "axiom_rules_repo": str(tmp_path),
            "parameters": {"euromod_country": "BE"},
        },
    }

    block = run_comparison._build_run_provenance(
        config, "euromod-synthetic-compare", output
    )
    assert "engine" not in block
    run_comparison._stamp_report_provenance(output, block)
    assert json.loads(output.read_text())["engines"]["versions"] == {
        "axiom_rules_engine": "0.1.0"
    }

    # A real run still records, and labels the report with, the engine it ran.
    config["runner"].pop("_reemitted_report")
    block = run_comparison._build_run_provenance(
        config, "euromod-synthetic-compare", output
    )
    assert block["engine"]["axiom_rules_engine_version"] == "0.2.2"
    run_comparison._stamp_report_provenance(output, block)
    assert json.loads(output.read_text())["engines"]["versions"] == {
        "axiom_rules_engine": "0.2.2"
    }
