"""Tests for the affected-comparison map generator and selector (O2)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"


def _load(name: str):
    module_path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --- generate_affected_map --------------------------------------------------


def test_repo_from_path_and_prefix():
    gam = _load("generate_affected_map.py")
    assert gam._repo_from_path("$HOME/roots/rulespec-us-co") == (
        "TheAxiomFoundation/rulespec-us-co"
    )
    assert gam._repo_from_prefix("us-co") == "TheAxiomFoundation/rulespec-us-co"
    assert gam._repo_from_prefix("uk") == "TheAxiomFoundation/rulespec-uk"
    # NEGATIVE: a non-rulespec directory contributes no repo.
    assert gam._repo_from_path("$HOME/some/other/dir") is None


def test_dir_alias_collapses_official_uk():
    gam = _load("generate_affected_map.py")
    assert gam._repo_from_path("$HOME/rulespec-uk-official") == (
        "TheAxiomFoundation/rulespec-uk"
    )


def test_generator_and_provenance_share_one_slug_function():
    """The affected-map generator and the report stamper MUST canonicalize
    rulespec slugs identically — otherwise the rerun selector silently fails to
    match a suite to its repo. Proven by them being the same function object.
    """
    gam = _load("generate_affected_map.py")
    from axiom_oracles.provenance import canonical_rulespec_slug

    assert gam._slug is canonical_rulespec_slug
    for name in ("rulespec-us", "rulespec-us-co", "rulespec-uk-official"):
        assert gam._slug(name) == canonical_rulespec_slug(name)


def test_concept_prefix_without_colon_yields_no_repo():
    """NEGATIVE: a colonless concept must not mint a garbage rulespec slug."""
    gam = _load("generate_affected_map.py")
    assert gam._concept_prefix("co_tanf_benefit") is None
    repos = gam.repos_for_registry_config(
        {
            "name": "x",
            "runner": {
                "type": "axiom-oracles-compare",
                "parameters": {"concepts": ["co_tanf_benefit"]},
            },
        }
    )
    assert repos == set()


def test_concept_prefix_maps_to_repo():
    gam = _load("generate_affected_map.py")
    repos = gam.repos_for_registry_config(
        {
            "name": "co-tanf-ecps",
            "runner": {
                "type": "axiom-oracles-compare",
                "parameters": {
                    "concepts": ["us-co:policies/cdhs/colorado-works#co_tanf_benefit"],
                },
            },
        }
    )
    assert "TheAxiomFoundation/rulespec-us-co" in repos


def test_snap_encoder_lane_adds_state_and_federal():
    gam = _load("generate_affected_map.py")
    repos = gam.repos_for_registry_config(
        {
            "name": "ca-snap-ecps",
            "runner": {
                "type": "axiom-encode-snap-ecps-compare",
                "parameters": {"jurisdiction": "us-ca"},
            },
        }
    )
    assert repos == {
        "TheAxiomFoundation/rulespec-us",
        "TheAxiomFoundation/rulespec-us-ca",
    }


def test_build_map_is_deterministic_and_check_passes():
    gam = _load("generate_affected_map.py")
    first = json.dumps(gam.build_map(), indent=2)
    second = json.dumps(gam.build_map(), indent=2)
    assert first == second
    # The committed file must already be current (CI runs --check).
    committed = gam.OUTPUT_PATH.read_text()
    assert committed == first + "\n"


def test_check_detects_drift(tmp_path, monkeypatch, capsys):
    """NEGATIVE: a stale committed map makes --check fail."""
    gam = _load("generate_affected_map.py")
    stale = tmp_path / "affected_map.json"
    stale.write_text('{"schema": "wrong", "suites": []}\n')
    monkeypatch.setattr(gam, "OUTPUT_PATH", stale)
    monkeypatch.setattr("sys.argv", ["generate_affected_map.py", "--check"])
    assert gam.main() == 1
    assert "stale" in capsys.readouterr().err


def test_parameter_suite_entries_use_file_prefix():
    gam = _load("generate_affected_map.py")
    entries = gam.parameter_suite_entries(
        {
            "suites": [
                {
                    "suite": "ga-health-thresholds",
                    "comparisons": [
                        {"file": "us-ga/policies/cms/x.yaml"},
                        {"file": "us-ga/policies/cms/y.yaml"},
                    ],
                }
            ]
        }
    )
    assert entries[0]["repos"] == ["TheAxiomFoundation/rulespec-us-ga"]
    assert entries[0]["report"] == "axiom-policyengine-ga-health-thresholds.json"


# --- select_affected_suites -------------------------------------------------

AFF_MAP = {
    "suites": [
        {"suite": "s1", "repos": ["owner/rulespec-us"]},
        {"suite": "s2", "repos": ["owner/rulespec-us", "owner/rulespec-us-co"]},
        {"suite": "no-repos", "repos": []},
    ]
}


def _report(suite, rulespecs):
    return {"suite": suite, "provenance": {"rulespecs": rulespecs}}


def test_selector_skips_fresh_suite():
    sel = _load("select_affected_suites.py")
    heads = {"owner/rulespec-us": "aaa"}
    reports = {"s1": _report("s1", [{"repo": "owner/rulespec-us", "sha": "aaa"}])}
    selected = sel.select(AFF_MAP, heads, reports)
    # s1 is fresh (SHA matches HEAD); no-repos is unmapped; s2 has no report.
    names = {s["suite"] for s in selected}
    assert "s1" not in names
    assert "s2" in names  # missing report → selected


def test_selector_selects_moved_sha():
    """NEGATIVE (staleness): a moved rules SHA forces a rerun."""
    sel = _load("select_affected_suites.py")
    heads = {"owner/rulespec-us": "bbb"}
    reports = {"s1": _report("s1", [{"repo": "owner/rulespec-us", "sha": "aaa"}])}
    selected = sel.select(AFF_MAP, heads, reports)
    s1 = next(s for s in selected if s["suite"] == "s1")
    assert "aaa" in s1["reason"] and "bbb" in s1["reason"]


def test_selector_selects_null_sha():
    sel = _load("select_affected_suites.py")
    heads = {"owner/rulespec-us": "bbb"}
    reports = {"s1": _report("s1", [{"repo": "owner/rulespec-us", "sha": None}])}
    selected = sel.select(AFF_MAP, heads, reports)
    assert any(s["suite"] == "s1" for s in selected)


def test_selector_selects_report_without_provenance():
    sel = _load("select_affected_suites.py")
    reports = {"s1": {"suite": "s1"}}
    selected = sel.select(AFF_MAP, {"owner/rulespec-us": "x"}, reports)
    s1 = next(s for s in selected if s["suite"] == "s1")
    assert "no provenance" in s1["reason"]


def test_selector_unknown_head_does_not_force_rerun():
    """A repo whose HEAD wasn't resolved must not force a spurious rerun."""
    sel = _load("select_affected_suites.py")
    reports = {"s1": _report("s1", [{"repo": "owner/rulespec-us", "sha": "aaa"}])}
    selected = sel.select(AFF_MAP, {}, reports)  # no heads at all
    assert not any(s["suite"] == "s1" for s in selected)
