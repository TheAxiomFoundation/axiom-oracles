"""Tests for the affected-comparison map generator and selector (O2)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

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


def test_direct_oracle_baseline_has_no_rulespec_dependency():
    """A EUROMOD↔GETTSIM baseline names DE concepts but runs no RuleSpec."""

    gam = _load("generate_affected_map.py")
    repos = gam.repos_for_registry_config(
        {
            "name": "de-worker-dual-oracle",
            "runner": {
                "type": "gettsim-synthetic-compare",
                "parameters": {
                    "concepts": [
                        "de:policies/worker_dual_oracle_baseline#kindergeld_monthly"
                    ],
                },
            },
        }
    )

    assert repos == set()


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


def test_campaign_projection_suite_is_manual_and_rulespec_affected():
    gam = _load("generate_affected_map.py")
    entries = gam.campaign_projection_suite_entries(
        {
            "rulespec_repos": ["TheAxiomFoundation/rulespec-us"],
            "suites": [
                {
                    "suite": "ct-income-tax-populace",
                    "report": "axiom-policyengine-ct-income-tax-populace.json",
                },
                {
                    "suite": "ga-income-tax-populace",
                    "report": "axiom-policyengine-ga-income-tax-populace.json",
                },
                {
                    "suite": "ms-income-tax-populace",
                    "report": "axiom-policyengine-ms-income-tax-populace.json",
                }
            ],
        },
        Path("state-income-tax-populace.yaml"),
    )

    assert entries == [
        {
            "suite": "ct-income-tax-populace",
            "name": None,
            "report": "axiom-policyengine-ct-income-tax-populace.json",
            "repos": ["TheAxiomFoundation/rulespec-us"],
            "source": "comparisons/state-income-tax-populace.yaml",
        },
        {
            "suite": "ga-income-tax-populace",
            "name": None,
            "report": "axiom-policyengine-ga-income-tax-populace.json",
            "repos": ["TheAxiomFoundation/rulespec-us"],
            "source": "comparisons/state-income-tax-populace.yaml",
        },
        {
            "suite": "ms-income-tax-populace",
            "name": None,
            "report": "axiom-policyengine-ms-income-tax-populace.json",
            "repos": ["TheAxiomFoundation/rulespec-us"],
            "source": "comparisons/state-income-tax-populace.yaml",
        },
    ]


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
        {"suite": "s1", "name": "s1", "repos": ["owner/rulespec-us"]},
        {
            "suite": "s2",
            "name": "s2",
            "repos": ["owner/rulespec-us", "owner/rulespec-us-co"],
        },
        {"suite": "no-repos", "name": "no-repos", "repos": []},
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


# --- runnable names: what the rerun matrix may dispatch ----------------------
#
# The 2026-07-20/21 affected reruns crashed ~50 matrix legs with "unknown
# comparison": the matrix dispatched dashboard suite keys (uk-benefit-cap) and
# parameter-lane suite names (ssi-parameters), neither of which
# run_comparison.py knows. The map now records each entry's registry `name`
# (null = not CI-runnable) and the selector dispatches exactly those.


def test_map_registry_entries_carry_their_registry_name():
    gen = _load("generate_affected_map.py")
    entries = {e["suite"]: e for e in gen.build_map()["suites"]}
    # Dashboard suite key and registry name differ for the ukmod suites —
    # dispatching the suite key is exactly the "unknown comparison" crash.
    assert entries["uk-benefit-cap"]["name"] == "uk-benefit-cap-ukmod"
    # Parameter suites have no registry runner: run_parameter_comparisons.py
    # (manual lane) owns them, so the map must mark them non-dispatchable.
    assert entries["ssi-parameters"]["name"] is None
    assert all("name" in e for e in entries.values())


def test_de_axiom_pair_map_entries_keep_exact_names_and_canonical_reports():
    """The DE pair suites dispatch their registry names, not the shared
    population key, and select freshness from their stable unified records."""

    gen = _load("generate_affected_map.py")
    entries = {entry["suite"]: entry for entry in gen.build_map()["suites"]}
    expected = {
        "de-worker-dual-oracle-axiom-euromod": (
            "comparisons/de-worker-dual-oracle/axiom-euromod.json"
        ),
        "de-worker-dual-oracle-axiom-gettsim": (
            "comparisons/de-worker-dual-oracle/axiom-gettsim.json"
        ),
    }

    for name, report in expected.items():
        entry = entries[name]
        assert entry["name"] == name
        assert entry["source"] == f"comparisons/{name}.yaml"
        assert entry["report"] == report
        assert entry["repos"] == ["TheAxiomFoundation/rulespec-de"]


def test_selector_decisions_carry_the_registry_name():
    sel = _load("select_affected_suites.py")
    amap = {
        "suites": [
            {
                "suite": "uk-benefit-cap",
                "name": "uk-benefit-cap-ukmod",
                "repos": ["owner/rulespec-uk"],
            }
        ]
    }
    selected = sel.select(amap, {"owner/rulespec-uk": "bbb"}, {})
    assert selected[0]["name"] == "uk-benefit-cap-ukmod"


def test_selector_loads_explicit_repo_relative_report(monkeypatch, tmp_path):
    """Canonical comparison records are selector inputs even though they are
    not dashboard reports."""

    sel = _load("select_affected_suites.py")
    repo = tmp_path / "repo"
    dashboard = repo / "dashboard" / "public" / "data"
    canonical = repo / "comparisons" / "de-worker-dual-oracle" / "leg.json"
    dashboard.mkdir(parents=True)
    canonical.parent.mkdir(parents=True)
    canonical.write_text(
        json.dumps(
            {
                "suite": "de-worker-dual-oracle-axiom-euromod",
                "provenance": {
                    "rulespecs": [
                        {
                            "repo": "TheAxiomFoundation/rulespec-de",
                            "sha": "a" * 40,
                        }
                    ]
                },
            }
        )
    )
    monkeypatch.setattr(sel, "REPO_ROOT", repo)
    monkeypatch.setattr(sel, "DASHBOARD_DATA_DIR", dashboard)
    affected_map = {
        "suites": [
            {
                "suite": "de-worker-dual-oracle-axiom-euromod",
                "name": "de-worker-dual-oracle-axiom-euromod",
                "report": "comparisons/de-worker-dual-oracle/leg.json",
                "repos": ["TheAxiomFoundation/rulespec-de"],
            }
        ]
    }

    reports = sel.load_reports(affected_map)

    assert reports["de-worker-dual-oracle-axiom-euromod"]["provenance"] == {
        "rulespecs": [
            {
                "repo": "TheAxiomFoundation/rulespec-de",
                "sha": "a" * 40,
            }
        ]
    }


@pytest.mark.parametrize(
    "unsafe",
    [
        "",
        "/tmp/outside.json",
        "../outside.json",
        "comparisons/../../outside.json",
        17,
    ],
)
def test_selector_rejects_unsafe_or_malformed_report_paths(unsafe):
    sel = _load("select_affected_suites.py")

    with pytest.raises(SystemExit, match="report path"):
        sel._selector_report_path(unsafe)


def test_selector_rejects_report_path_through_escaping_symlink(
    monkeypatch, tmp_path
):
    sel = _load("select_affected_suites.py")
    repo = tmp_path / "repo"
    comparisons = repo / "comparisons"
    outside = tmp_path / "outside"
    comparisons.mkdir(parents=True)
    outside.mkdir()
    (comparisons / "escape").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(sel, "REPO_ROOT", repo)

    with pytest.raises(SystemExit, match="escapes the repo"):
        sel._selector_report_path("comparisons/escape/record.json")


def test_runnable_names_dispatches_registry_names_not_suite_keys():
    sel = _load("select_affected_suites.py")
    selected = [
        {"suite": "uk-benefit-cap", "name": "uk-benefit-cap-ukmod"},
        {"suite": "s1", "name": "s1"},
        {"suite": "ssi-parameters", "name": None},  # manual parameter lane
        {"suite": "s1-again", "name": "s1"},  # duplicate runner
    ]
    assert sel.runnable_names(selected) == ["uk-benefit-cap-ukmod", "s1"]
    assert sel.manual_suites(selected) == ["ssi-parameters"]


@pytest.mark.parametrize(
    "bad_entry",
    [
        {"suite": "drifted", "repos": ["o/r"]},  # name key missing entirely
        {"suite": "empty", "name": "", "repos": ["o/r"]},
        {"suite": "blank", "name": "   ", "repos": ["o/r"]},
        {"suite": "zero", "name": 0, "repos": ["o/r"]},
        {"suite": "false", "name": False, "repos": ["o/r"]},
        {"suite": "number", "name": 123, "repos": ["o/r"]},
        {"suite": "list", "name": ["x"], "repos": ["o/r"]},
    ],
)
def test_selection_fails_loudly_on_malformed_name(bad_entry):
    """NEGATIVE: only an explicit JSON null means "manual lane". A missing or
    malformed `name` is map drift — silently skipping it would shrink the
    matrix while looking green, so both selection paths must fail loudly."""
    sel = _load("select_affected_suites.py")
    amap = {"suites": [bad_entry]}
    with pytest.raises(SystemExit, match="regenerate"):
        sel.select(amap, {}, {})
    with pytest.raises(SystemExit, match="regenerate"):
        sel.force_all_selection(amap)


def test_force_all_matches_normal_dispatch_rules():
    """force_all selects every repo-bearing entry — same validation, same
    null-name manual routing, same dedup — so the workflow's two paths cannot
    drift (the old inline force_all branch dispatched raw suite keys)."""
    sel = _load("select_affected_suites.py")
    amap = {
        "suites": [
            {"suite": "uk-x", "name": "uk-x-ukmod", "repos": ["o/uk"]},
            {"suite": "manual", "name": None, "repos": ["o/us"]},
            {"suite": "plain", "name": "plain", "repos": ["o/us"]},
            {"suite": "unmapped", "name": "unmapped", "repos": []},
        ]
    }
    selected = sel.force_all_selection(amap)
    assert [d["suite"] for d in selected] == ["uk-x", "manual", "plain"]
    assert all(d["reason"] == "force_all" for d in selected)
    assert sel.runnable_names(selected) == ["uk-x-ukmod", "plain"]
    assert sel.manual_suites(selected) == ["manual"]


def test_github_format_emits_output_lines(monkeypatch, capsys):
    """The workflow consumes the selector via --format github: one
    $GITHUB_OUTPUT line per key, matrix JSON single-line, manual accounting
    present."""
    sel = _load("select_affected_suites.py")
    monkeypatch.setattr(
        sel.sys,
        "argv",
        ["select_affected_suites.py", "--force-all", "--format", "github"],
    )
    assert sel.main() == 0
    out = capsys.readouterr().out.splitlines()
    keys = dict(line.split("=", 1) for line in out if "=" in line)
    matrix = json.loads(keys["matrix"])
    assert int(keys["count"]) == len(matrix["include"]) > 0
    assert int(keys["manual_count"]) == len(keys["manual"].split())
    assert "ssi-parameters" in keys["manual"]


def test_every_runnable_map_name_resolves_in_the_registry():
    """EXHAUSTIVE: every non-null name in a fresh build_map() must load
    through run_comparison.py's real resolver (config file exists, internal
    name matches, runner registered) — the invariant whose violation crashed
    ~50 matrix legs per run. Also pins uniqueness: duplicate registry names
    across map entries would silently collapse into one leg."""
    gen = _load("generate_affected_map.py")
    rc = _load("run_comparison.py")
    entries = gen.build_map()["suites"]

    names = [e["name"] for e in entries if e["name"] is not None]
    assert len(names) == len(set(names)), "duplicate registry names in the map"
    suites = [e["suite"] for e in entries]
    assert len(suites) == len(set(suites)), "duplicate suite keys in the map"

    for name in names:
        config = rc._load_comparison(name)  # raises on unknown comparison
        assert config["name"] == name, (
            f"{name}: config file stem and internal name diverge"
        )
        assert config["runner"]["type"] in rc.RUNNERS, (
            f"{name}: runner type {config['runner']['type']!r} not registered"
        )

    for entry in entries:
        if entry["name"] is None:
            if entry["source"] == "comparisons/parameter-oracles.yaml":
                continue
            # The only other legitimate non-runnable class: a registry suite
            # explicitly declaring `ci: manual` in its own YAML (#296).
            import yaml

            config = yaml.safe_load(
                (Path(__file__).parents[1] / entry["source"]).read_text()
            )
            assert config.get("ci") == "manual", (
                f"{entry['suite']}: non-runnable entries must be parameter "
                "suites or declare `ci: manual`"
            )


def test_ci_manual_registry_suite_emits_null_name():
    """A registry suite declaring `ci: manual` must be routed to the manual
    lane exactly like a parameter suite: `name: null`, excluded from both the
    6-hourly rerun matrix and the weekly matrix. or/ut SNAP carry the marker
    for a missing encoder jurisdiction config (#296/#336); the engine-main ×
    rulespec-us-main suites carry it while the upstream chain is broken
    (#455)."""
    gen = _load("generate_affected_map.py")
    entries = {e["suite"]: e for e in gen.build_map()["suites"]}
    assert entries["or-snap-ecps"]["name"] is None
    assert entries["ut-snap-ecps"]["name"] is None
    # The engine-main × rulespec-us-main suites are manual until the #455
    # upstream chain lands.
    assert entries["az-snap-ecps"]["name"] is None
    assert entries["co-snap-ecps"]["name"] is None
    # A dispatchable registry suite keeps its name (UK lane, unaffected).
    assert entries["uk-benefit-cap"]["name"] == "uk-benefit-cap-ukmod"


def test_direct_oracle_pair_suites_carry_no_rulespec_dependency():
    """An axiom-oracles-compare suite with no `axiom` side executes no
    RuleSpec, so rules movement cannot change its numbers — mapping concept
    prefixes to repos would re-select it every time rulespec-us moves, only to
    re-emit the same numbers (#296)."""
    gen = _load("generate_affected_map.py")
    entries = {e["suite"]: e for e in gen.build_map()["suites"]}
    assert entries["taxcalc-fiit-ecps"]["repos"] == []
    # An axiom-sided compare over the same concept space keeps its mapping.
    assert (
        "TheAxiomFoundation/rulespec-us"
        in entries["co-state-income-tax-taxsim"]["repos"]
    )


# --- pinned-suite freshness (#455 lane: pinned grids vs moving HEAD) ---------


def test_pinned_repos_for_registry_config():
    gen = _load("generate_affected_map.py")
    config = {
        "name": "us-x-grid",
        "runner": {
            "type": "federal-tax-liability-grid",
            "parameters": {
                "rulespec_remote": (
                    "https://github.com/TheAxiomFoundation/rulespec-us.git"
                ),
                "rulespec_roots": ["$HOME/TheAxiomFoundation/rulespec-us"],
                "rulespec_upstream_sha": "c" * 40,
                "rulespec_upstream_tree": "d" * 40,
            },
        },
    }
    assert gen.pinned_repos_for_registry_config(config) == {
        "TheAxiomFoundation/rulespec-us": "c" * 40
    }
    config["runner"]["parameters"].pop("rulespec_upstream_sha")
    assert gen.pinned_repos_for_registry_config(config) == {}


def test_pinned_repos_ambiguity_fails_loudly():
    gen = _load("generate_affected_map.py")
    config = {
        "name": "bad",
        "runner": {
            "parameters": {
                "rulespec_upstream_sha": "c" * 40,
                "rulespec_roots": ["$HOME/rulespec-us", "$HOME/rulespec-uk"],
            }
        },
    }
    with pytest.raises(SystemExit):
        gen.pinned_repos_for_registry_config(config)


def test_selector_pinned_repo_judged_against_pin_not_head():
    """A pinned grid's report stamps the pin; HEAD movement must not select it."""
    sel = _load("select_affected_suites.py")
    aff = {
        "suites": [
            {
                "suite": "s1",
                "name": "s1",
                "repos": ["owner/rulespec-us"],
                "pinned": {"owner/rulespec-us": "ppp"},
            }
        ]
    }
    heads = {"owner/rulespec-us": "bbb"}  # main moved past the pin
    reports = {"s1": _report("s1", [{"repo": "owner/rulespec-us", "sha": "ppp"}])}
    assert sel.select(aff, heads, reports) == []


def test_selector_pinned_repo_stale_when_pin_changes():
    """A deliberate re-pin PR is exactly what makes a pinned suite stale."""
    sel = _load("select_affected_suites.py")
    aff = {
        "suites": [
            {
                "suite": "s1",
                "name": "s1",
                "repos": ["owner/rulespec-us"],
                "pinned": {"owner/rulespec-us": "qqq"},
            }
        ]
    }
    heads = {"owner/rulespec-us": "qqq"}
    reports = {"s1": _report("s1", [{"repo": "owner/rulespec-us", "sha": "ppp"}])}
    selected = sel.select(aff, heads, reports)
    assert [s["suite"] for s in selected] == ["s1"]
    assert "pin" in selected[0]["reason"]


def test_selector_pinned_repo_unknown_sha_still_selected():
    sel = _load("select_affected_suites.py")
    aff = {
        "suites": [
            {
                "suite": "s1",
                "name": "s1",
                "repos": ["owner/rulespec-us"],
                "pinned": {"owner/rulespec-us": "qqq"},
            }
        ]
    }
    reports = {"s1": _report("s1", [{"repo": "owner/rulespec-us", "sha": None}])}
    assert [s["suite"] for s in sel.select(aff, {}, reports)] == ["s1"]
