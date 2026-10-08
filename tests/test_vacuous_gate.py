"""Tests for the vacuous-verification gate (O3).

Every gate here carries at least one NEGATIVE test proving the gate actually
fails when its invariant is violated — a gate that cannot fail would itself be
vacuous verification of vacuous verification.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"


def _load_gate():
    module_path = SCRIPTS / "check_vacuous_gate.py"
    spec = importlib.util.spec_from_file_location("check_vacuous_gate", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --- Guard 1: oracle-backed config check ------------------------------------


def test_real_policyengine_config_passes():
    gate = _load_gate()
    problems = gate._config_oracle_problems(
        "fiit-ecps",
        {"runner": {"type": "axiom-encode-tax-ecps-compare"}},
    )
    assert problems == []


def test_generic_compare_with_real_right_passes():
    gate = _load_gate()
    problems = gate._config_oracle_problems(
        "ssi-ecps",
        {
            "runner": {
                "type": "axiom-oracles-compare",
                "parameters": {"left": "axiom", "right": "policyengine"},
            }
        },
    )
    assert problems == []


def test_direct_oracle_crosscheck_runner_passes():
    gate = _load_gate()
    problems = gate._config_oracle_problems(
        "de-worker-dual-oracle",
        {"runner": {"type": "gettsim-synthetic-compare"}},
    )
    assert problems == []


def test_oracle_none_without_reason_fails():
    """NEGATIVE: opting out of an oracle requires a reason."""
    gate = _load_gate()
    problems = gate._config_oracle_problems("x", {"oracle": "none"})
    assert any("reason" in p for p in problems)


def test_oracle_none_with_reason_passes():
    gate = _load_gate()
    problems = gate._config_oracle_problems(
        "x", {"oracle": "none", "reason": "coverage-only surface, no oracle yet"}
    )
    assert problems == []


def test_missing_oracle_key_is_not_an_optout():
    """A config with no `oracle` key and an unknown runner must still fail —
    the absence of the key is not an opt-out."""
    gate = _load_gate()
    problems = gate._config_oracle_problems(
        "x", {"runner": {"type": "some-unknown-runner"}}
    )
    assert any("not a known oracle-backed runner" in p for p in problems)


def test_axiom_vs_axiom_fails():
    """NEGATIVE: comparing an engine against itself verifies nothing."""
    gate = _load_gate()
    problems = gate._config_oracle_problems(
        "x",
        {
            "runner": {
                "type": "axiom-oracles-compare",
                "parameters": {"left": "axiom", "right": "axiom"},
            }
        },
    )
    assert any("against" in p and "itself" in p for p in problems)


def test_generic_compare_missing_right_fails():
    """NEGATIVE: an empty right oracle is a vacuous comparison."""
    gate = _load_gate()
    problems = gate._config_oracle_problems(
        "x",
        {"runner": {"type": "axiom-oracles-compare", "parameters": {"left": "axiom"}}},
    )
    assert any("real `right:` oracle" in p for p in problems)


# --- Guard 1b: fixture oracle check -----------------------------------------


def test_fixture_with_expected_passes(tmp_path):
    gate = _load_gate()
    doc = {"fixtures": [{"id": "a", "expected": {"axiom": True}}]}
    problems = gate._fixture_oracle_problems(gate.REPO_ROOT / "x.fixtures.yaml", doc)
    assert problems == []


def test_fixture_without_expected_fails(tmp_path):
    """NEGATIVE: a fixture that declares no expected outcome verifies nothing."""
    gate = _load_gate()
    doc = {"fixtures": [{"id": "a"}]}
    problems = gate._fixture_oracle_problems(gate.REPO_ROOT / "x.fixtures.yaml", doc)
    assert any("verifies nothing" in p for p in problems)


def test_fixture_oracle_none_needs_reason():
    gate = _load_gate()
    doc = {"fixtures": [{"id": "a", "oracle": "none"}]}
    problems = gate._fixture_oracle_problems(gate.REPO_ROOT / "x.fixtures.yaml", doc)
    assert any("reason" in p for p in problems)
    # With a reason, it passes.
    doc2 = {"fixtures": [{"id": "a", "oracle": "none", "reason": "PE projection TBD"}]}
    assert gate._fixture_oracle_problems(gate.REPO_ROOT / "x.fixtures.yaml", doc2) == []


def test_empty_fixtures_file_fails():
    """NEGATIVE: a fixtures file with no cases is vacuous."""
    gate = _load_gate()
    problems = gate._fixture_oracle_problems(
        gate.REPO_ROOT / "x.fixtures.yaml", {"fixtures": []}
    )
    assert any("no fixtures" in p for p in problems)


def test_repo_configs_are_all_oracle_backed():
    """The committed comparison configs must pass the gate (guards the repo)."""
    gate = _load_gate()
    assert gate.check_oracle_backed() == []


def test_campaign_projection_declaration_fails_closed():
    gate = _load_gate()
    assert (
        "declares no suites"
        in gate._campaign_projection_problems("campaign.yaml", {"suites": []})[0]
    )
    problems = gate._campaign_projection_problems(
        "campaign.yaml",
        {
            "rulespec_repos": ["TheAxiomFoundation/rulespec-us"],
            "suites": [
                {
                    "suite": "ct-income-tax-populace",
                    "report": "ct.json",
                    "campaign_runner": "run.py",
                    "projector": "emit.py",
                    "oracle": "none",
                }
            ],
        },
    )
    assert any("has no oracle" in problem for problem in problems)


def _campaign_projection_fixture(gate, tmp_path, monkeypatch):
    root = tmp_path / "repo"
    data = root / "dashboard" / "public" / "data"
    reports = root / "reports"
    scripts = root / "scripts"
    for directory in (data, reports, scripts):
        directory.mkdir(parents=True, exist_ok=True)
    (scripts / "run.py").write_text("# runner\n")
    (scripts / "emit.py").write_text("# projector\n")

    rulespec = {
        "repository": "TheAxiomFoundation/rulespec-us",
        "commit": "1" * 40,
        "working_tree": "clean",
    }
    runtime = {
        "rulespec": rulespec,
        "axiom_engine": {
            "repository": "TheAxiomFoundation/axiom-rules-engine",
            "commit": "2" * 40,
            "executable_sha256": "4" * 64,
            "working_tree": "clean",
        },
        "packages": {
            "policyengine": "4.18.9",
            "policyengine-us": "1.752.2",
        },
    }
    dataset = {
        "source": "pinned",
        "revision": "populace-us-test",
        "sha256": "3" * 12,
        "built_with": "1.729.0",
        "country": "us",
    }
    state_entry = {
        "compared_count": 2,
        "mismatch_count": 0,
        "mismatches": [],
        "output": "us-ct:policies/income_tax/example#output",
        "program": "ct-program",
        "policyengine_target": "ct_target",
        "tolerance": 0.01,
        "relative_tolerance": 1e-7,
        "max_absolute_difference": 0.0,
        "weighted_compared_tax_units": 2.0,
    }
    campaign = {
        "schema_version": "axiom.state_tax_populace_campaign_report.v1",
        "generated_at": "2026-07-26T12:00:00Z",
        "generated_by": "scripts/run.py",
        "run_kind": "manual",
        "runtime_provenance": runtime,
        "dataset_identity": dataset,
        "requested_states": ["CT"],
        "comparison": {"states": {"CT": state_entry}},
    }
    (reports / "campaign.json").write_text(json.dumps(campaign))
    report = {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "ct-income-tax-populace",
        "case_count": 2,
        "population": "populace-us",
        "engines": {"axiom": "ct-program", "policyengine": "ct_target"},
        "aggregates": [
            {
                "concept": state_entry["output"],
                "comparison_count": 2,
                "compared": 2,
                "match_count": 2,
                "matched": 2,
                "mismatch_count": 0,
                "match_rate": 100.0,
                "weighted_match_rate": 100.0,
            }
        ],
        "mismatches": [],
        "summary": {
            "comparison_count": 2,
            "match_count": 2,
            "match_rate": 100.0,
            "mismatch_count": 0,
        },
        "provenance": {
            "schema": "axiom_oracles.provenance.v1",
            "generated_at": campaign["generated_at"],
            "generated_by": ("scripts/emit.py::ct-income-tax-populace"),
            "run_kind": campaign["run_kind"],
            "campaign_report": "campaign.json",
            "rulespecs": [
                {
                    "repo": rulespec["repository"],
                    "sha": rulespec["commit"],
                }
            ],
            "runtime_provenance": runtime,
            "dataset_identity": dataset,
            "tolerance": state_entry["tolerance"],
            "relative_tolerance": state_entry["relative_tolerance"],
            "max_absolute_difference": state_entry["max_absolute_difference"],
            "weighted_compared_tax_units": state_entry[
                "weighted_compared_tax_units"
            ],
        },
    }
    report_path = data / "ct.json"
    report_path.write_text(json.dumps(report))

    monkeypatch.setattr(gate, "REPO_ROOT", root)
    monkeypatch.setattr(gate, "DASHBOARD_DATA_DIR", data)
    monkeypatch.setattr(gate, "REPORTS_DIR", reports)
    config = {
        "rulespec_repos": ["TheAxiomFoundation/rulespec-us"],
        "suites": [
            {
                "suite": "ct-income-tax-populace",
                "report": "ct.json",
                "campaign_runner": "scripts/run.py",
                "projector": "scripts/emit.py",
                "oracle": "policyengine",
                "jurisdiction": "CT",
                "program": "state_income_tax",
            }
        ],
    }
    return config, report_path, scripts


def test_campaign_projection_chain_validates_end_to_end(tmp_path, monkeypatch):
    gate = _load_gate()
    config, _, _ = _campaign_projection_fixture(gate, tmp_path, monkeypatch)
    assert gate._campaign_projection_problems("campaign.yaml", config) == []


@pytest.mark.parametrize(
    ("field", "relative"),
    [
        ("campaign_runner", "scripts/missing-runner.py"),
        ("projector", "scripts/missing-projector.py"),
        ("report", "missing-report.json"),
    ],
)
def test_campaign_projection_rejects_typo_or_deleted_paths(
    tmp_path, monkeypatch, field, relative
):
    gate = _load_gate()
    config, _, _ = _campaign_projection_fixture(gate, tmp_path, monkeypatch)
    config["suites"][0][field] = relative

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any("path does not exist" in problem for problem in problems)


def test_campaign_projection_rejects_deleted_report(tmp_path, monkeypatch):
    gate = _load_gate()
    config, report_path, _ = _campaign_projection_fixture(gate, tmp_path, monkeypatch)
    report_path.unlink()

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any("report path does not exist" in problem for problem in problems)


def test_campaign_projection_rejects_report_misalignment(tmp_path, monkeypatch):
    gate = _load_gate()
    config, report_path, _ = _campaign_projection_fixture(gate, tmp_path, monkeypatch)
    report = json.loads(report_path.read_text())
    report["schema_version"] = "wrong"
    report["suite"] = "wrong-suite"
    report["engines"].pop("policyengine")
    report["provenance"]["schema"] = "wrong"
    report["provenance"]["generated_by"] = "scripts/wrong.py::wrong-suite"
    report["provenance"]["generated_at"] = "2026-07-26T12:00:01Z"
    report["provenance"]["run_kind"] = "weekly"
    report["provenance"]["rulespecs"][0]["repo"] = "TheAxiomFoundation/rulespec-us-ct"
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    joined = "\n".join(problems)
    assert "report schema" in joined
    assert "report suite" in joined
    assert "declared oracle" in joined
    assert "invalid provenance schema" in joined
    assert "generated_by does not align with projector" in joined
    assert "RuleSpec repos" in joined
    assert "generated_at does not align" in joined
    assert "run_kind does not align" in joined
    assert "RuleSpec provenance does not align" in joined


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("axiom_engine", "commit", "4" * 40),
        ("packages", "policyengine-us", "9.9.9"),
    ],
)
def test_campaign_projection_rejects_runtime_identity_mutation(
    tmp_path, monkeypatch, section, key, value
):
    gate = _load_gate()
    config, report_path, _ = _campaign_projection_fixture(gate, tmp_path, monkeypatch)
    report = json.loads(report_path.read_text())
    report["provenance"]["runtime_provenance"][section][key] = value
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any(
        "runtime_provenance does not exactly align" in problem for problem in problems
    )


def test_campaign_projection_rejects_dataset_revision_mutation(tmp_path, monkeypatch):
    gate = _load_gate()
    config, report_path, _ = _campaign_projection_fixture(gate, tmp_path, monkeypatch)
    report = json.loads(report_path.read_text())
    report["provenance"]["dataset_identity"]["revision"] = "tampered"
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any(
        "dataset_identity does not exactly align" in problem for problem in problems
    )


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("rulespec", "working_tree"),
        ("axiom_engine", "executable_sha256"),
        ("axiom_engine", "working_tree"),
        ("packages", "policyengine"),
    ],
)
def test_campaign_projection_rejects_runtime_identity_omitted_from_both_artifacts(
    tmp_path, monkeypatch, section, field
):
    """Equality cannot hide an identity field omitted on both sides."""

    gate = _load_gate()
    config, report_path, scripts = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    campaign_path = scripts.parent / "reports" / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    report = json.loads(report_path.read_text())
    campaign["runtime_provenance"][section].pop(field)
    report["provenance"]["runtime_provenance"][section].pop(field)
    campaign_path.write_text(json.dumps(campaign))
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any(
        f"runtime_provenance.{section} is missing {field}" in problem
        for problem in problems
    )


def test_campaign_projection_rejects_non_string_runtime_identity_on_both_sides(
    tmp_path, monkeypatch
):
    gate = _load_gate()
    config, report_path, scripts = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    campaign_path = scripts.parent / "reports" / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    report = json.loads(report_path.read_text())
    campaign["runtime_provenance"]["axiom_engine"]["executable_sha256"] = True
    report["provenance"]["runtime_provenance"]["axiom_engine"][
        "executable_sha256"
    ] = True
    campaign_path.write_text(json.dumps(campaign))
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any(
        "runtime_provenance.axiom_engine is missing executable_sha256" in p
        for p in problems
    )


@pytest.mark.parametrize("field", ["source", "built_with", "country"])
def test_campaign_projection_rejects_dataset_identity_omitted_from_both_artifacts(
    tmp_path, monkeypatch, field
):
    gate = _load_gate()
    config, report_path, scripts = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    campaign_path = scripts.parent / "reports" / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    report = json.loads(report_path.read_text())
    campaign["dataset_identity"].pop(field)
    report["provenance"]["dataset_identity"].pop(field)
    campaign_path.write_text(json.dumps(campaign))
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any(f"dataset_identity is missing {field}" in problem for problem in problems)


def test_campaign_projection_rejects_non_string_dataset_identity_on_both_sides(
    tmp_path, monkeypatch
):
    gate = _load_gate()
    config, report_path, scripts = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    campaign_path = scripts.parent / "reports" / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    report = json.loads(report_path.read_text())
    campaign["dataset_identity"]["sha256"] = True
    report["provenance"]["dataset_identity"]["sha256"] = True
    campaign_path.write_text(json.dumps(campaign))
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any("dataset_identity is missing sha256" in p for p in problems)


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (("case_count",), 0, "case_count does not align"),
        (("engines", "axiom"), "wrong-program", "Axiom program does not align"),
        (
            ("engines", "policyengine"),
            "wrong-target",
            "oracle target does not align",
        ),
        (("summary", "comparison_count"), 0, "summary does not align"),
        (("aggregates", 0, "concept"), "wrong-output", "aggregate does not align"),
        (
            ("mismatches",),
            [{"tax_unit_id": 1}],
            "mismatches do not align",
        ),
    ],
)
def test_campaign_projection_rejects_tampered_semantic_projection(
    tmp_path, monkeypatch, path, value, expected
):
    gate = _load_gate()
    config, report_path, _ = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    report = json.loads(report_path.read_text())
    target = report
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any(expected in problem for problem in problems)


@pytest.mark.parametrize(
    ("field", "report_section", "report_field"),
    [
        ("program", "engines", "axiom"),
        ("policyengine_target", "engines", "policyengine"),
        ("output", "aggregates", "concept"),
    ],
)
def test_campaign_projection_rejects_semantic_identity_omitted_from_both_artifacts(
    tmp_path, monkeypatch, field, report_section, report_field
):
    gate = _load_gate()
    config, report_path, scripts = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    campaign_path = scripts.parent / "reports" / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    campaign["comparison"]["states"]["CT"].pop(field)
    campaign_path.write_text(json.dumps(campaign))

    report = json.loads(report_path.read_text())
    if report_section == "aggregates":
        report[report_section][0].pop(report_field)
    else:
        report[report_section].pop(report_field)
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any(
        f"source campaign comparison state is missing {field}" in p for p in problems
    )


@pytest.mark.parametrize(
    "field",
    [
        "tolerance",
        "relative_tolerance",
        "max_absolute_difference",
        "weighted_compared_tax_units",
    ],
)
def test_campaign_projection_rejects_evidence_omitted_from_both_artifacts(
    tmp_path, monkeypatch, field
):
    gate = _load_gate()
    config, report_path, scripts = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    campaign_path = scripts.parent / "reports" / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    report = json.loads(report_path.read_text())
    campaign["comparison"]["states"]["CT"].pop(field)
    report["provenance"].pop(field)
    campaign_path.write_text(json.dumps(campaign))
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any(f"source campaign {field} must be a finite" in p for p in problems)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tolerance", "not-a-number"),
        ("relative_tolerance", -1.0),
        ("max_absolute_difference", -1.0),
        ("weighted_compared_tax_units", 0.0),
    ],
)
def test_campaign_projection_rejects_invalid_aligned_evidence(
    tmp_path, monkeypatch, field, value
):
    gate = _load_gate()
    config, report_path, scripts = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    campaign_path = scripts.parent / "reports" / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    report = json.loads(report_path.read_text())
    campaign["comparison"]["states"]["CT"][field] = value
    report["provenance"][field] = value
    campaign_path.write_text(json.dumps(campaign))
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any(f"source campaign {field} must be a finite" in p for p in problems)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (("provenance", "max_absolute_difference"), "provenance"),
        (("summary", "mismatch_count"), "summary"),
        (("aggregates", 0, "mismatch_count"), "aggregate"),
    ],
)
def test_campaign_projection_rejects_report_boolean_for_numeric_zero(
    tmp_path, monkeypatch, path, expected
):
    """Python's ``False == 0`` must not weaken exact JSON binding."""

    gate = _load_gate()
    config, report_path, _ = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    report = json.loads(report_path.read_text())
    target = report
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = False
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any(expected in p and "does not align" in p for p in problems)


def test_campaign_projection_rejects_report_boolean_for_case_count_one(
    tmp_path, monkeypatch
):
    gate = _load_gate()
    config, report_path, scripts = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    campaign_path = scripts.parent / "reports" / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    campaign["comparison"]["states"]["CT"]["compared_count"] = 1
    campaign_path.write_text(json.dumps(campaign))

    report = json.loads(report_path.read_text())
    report["case_count"] = True
    report["summary"].update({"comparison_count": 1, "match_count": 1})
    report["aggregates"][0].update(
        {
            "comparison_count": 1,
            "compared": 1,
            "match_count": 1,
            "matched": 1,
        }
    )
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any("report case_count does not align" in p for p in problems)


@pytest.mark.parametrize(
    ("field", "engine"),
    [
        ("program", "axiom"),
        ("policyengine_target", "policyengine"),
    ],
)
def test_campaign_projection_rejects_boolean_campaign_engine_identifier(
    tmp_path, monkeypatch, field, engine
):
    gate = _load_gate()
    config, report_path, scripts = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    campaign_path = scripts.parent / "reports" / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    campaign["comparison"]["states"]["CT"][field] = True
    campaign_path.write_text(json.dumps(campaign))

    report = json.loads(report_path.read_text())
    report["engines"][engine] = 1
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any(
        f"source campaign comparison state is missing {field}" in p for p in problems
    )
    expected = "Axiom program" if engine == "axiom" else "oracle target"
    assert any(f"report {expected} does not align" in p for p in problems)


def test_campaign_projection_rejects_boolean_campaign_output_identifier(
    tmp_path, monkeypatch
):
    gate = _load_gate()
    config, report_path, scripts = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    campaign_path = scripts.parent / "reports" / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    campaign["comparison"]["states"]["CT"]["output"] = True
    campaign_path.write_text(json.dumps(campaign))

    report = json.loads(report_path.read_text())
    report["aggregates"][0]["concept"] = 1
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any(
        "source campaign comparison state is missing output" in p for p in problems
    )
    assert any("report aggregate does not align" in p for p in problems)


def test_campaign_projection_rejects_mismatch_count_without_evidence_rows(
    tmp_path, monkeypatch
):
    gate = _load_gate()
    config, report_path, scripts = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    campaign_path = scripts.parent / "reports" / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    campaign["comparison"]["states"]["CT"]["mismatch_count"] = 1
    campaign_path.write_text(json.dumps(campaign))

    report = json.loads(report_path.read_text())
    report["summary"].update(
        {"match_count": 1, "match_rate": 50.0, "mismatch_count": 1}
    )
    report["aggregates"][0].update(
        {
            "match_count": 1,
            "matched": 1,
            "mismatch_count": 1,
            "match_rate": 50.0,
            "weighted_match_rate": 50.0,
        }
    )
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any("mismatch list length does not align" in p for p in problems)


def test_campaign_projection_rejects_zero_comparison_even_when_aligned(
    tmp_path, monkeypatch
):
    gate = _load_gate()
    config, report_path, scripts = _campaign_projection_fixture(
        gate, tmp_path, monkeypatch
    )
    campaign_path = scripts.parent / "reports" / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["CT"]
    state["compared_count"] = 0
    campaign_path.write_text(json.dumps(campaign))

    report = json.loads(report_path.read_text())
    report["case_count"] = 0
    report["summary"] = {
        "comparison_count": 0,
        "match_count": 0,
        "match_rate": 100.0,
        "mismatch_count": 0,
    }
    report["aggregates"][0].update(
        {
            "comparison_count": 0,
            "compared": 0,
            "match_count": 0,
            "matched": 0,
        }
    )
    report_path.write_text(json.dumps(report))

    problems = gate._campaign_projection_problems("campaign.yaml", config)
    assert any("compared_count must be a positive integer" in p for p in problems)


def test_declared_file_rejects_traversal(tmp_path):
    gate = _load_gate()
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    problems = []

    assert (
        gate._declared_file(
            root,
            "../outside.txt",
            label="fixture",
            problems=problems,
        )
        is None
    )
    assert any("escapes its declared root" in problem for problem in problems)


def test_declared_file_rejects_absolute_path(tmp_path):
    gate = _load_gate()
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    problems = []

    assert (
        gate._declared_file(
            root,
            str(outside),
            label="fixture",
            problems=problems,
        )
        is None
    )
    assert any("must be repo-relative" in problem for problem in problems)


# --- Guard 2: freshness age computation + alarms ----------------------------


def test_report_age_days_parses_provenance():
    gate = _load_gate()
    old = (datetime.now(timezone.utc) - timedelta(days=20)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    report = {"provenance": {"generated_at": old}}
    age = gate._report_age_days(report)
    assert 19 < age < 21


def test_report_age_days_none_when_unstamped():
    gate = _load_gate()
    assert gate._report_age_days({"suite": "x"}) is None


def test_suite_matches_program_national_marker():
    gate = _load_gate()
    # US-national federal income tax maps to the fiit suite.
    assert gate._suite_matches_program("fiit-ecps", "federal_income_tax", "US")
    # A state row requires the state token.
    assert gate._suite_matches_program("co-snap-ecps", "snap", "CO")
    # NEGATIVE: a different state does not match.
    assert not gate._suite_matches_program("co-snap-ecps", "snap", "NY")
    # NEGATIVE: CO must not match the "co" substring inside "income".
    assert not gate._suite_matches_program(
        "ct-income-tax-populace", "state_income_tax", "CO"
    )
    assert gate._suite_matches_program(
        "ct-income-tax-populace", "state_income_tax", "CT"
    )


def test_freshness_check_fails_when_committed_file_missing(monkeypatch, tmp_path):
    """NEGATIVE: --check fails if freshness.json is absent."""
    gate = _load_gate()
    monkeypatch.setattr(gate, "FRESHNESS_OUTPUT", tmp_path / "nope.json")
    monkeypatch.setattr("sys.argv", ["check_vacuous_gate.py", "--check"])
    assert gate.main() == 1


def test_freshness_comparable_ignores_top_level_wall_clock():
    gate = _load_gate()
    a = {
        "generated_at": "2026-01-01T00:00:00Z",
        "suites": [{"suite": "s", "generated_at": "2026-05-01T00:00:00Z"}],
        "executable_surfaces": [],
    }
    b = {
        "generated_at": "2026-02-02T00:00:00Z",  # different 'now'
        "suites": [{"suite": "s", "generated_at": "2026-05-01T00:00:00Z"}],
        "executable_surfaces": [],
    }
    # Same structure + same per-suite report timestamps, different doc 'now'
    # → comparable-equal (the doc-level generated_at is stripped).
    assert gate._freshness_comparable(a) == gate._freshness_comparable(b)


def test_freshness_comparable_detects_report_timestamp_change():
    """NEGATIVE: a changed per-suite report timestamp IS a real change.

    Per-suite generated_at is a report fact, so a rerun that moves it must make
    the committed file drift (and --check catch it) — unlike the doc 'now'.
    """
    gate = _load_gate()
    a = {"suites": [{"suite": "s", "generated_at": "2026-05-01T00:00:00Z"}]}
    b = {"suites": [{"suite": "s", "generated_at": "2026-06-01T00:00:00Z"}]}
    assert gate._freshness_comparable(a) != gate._freshness_comparable(b)


def test_build_freshness_stores_no_time_dependent_state(monkeypatch, tmp_path):
    """The whole point of the O2/O3 fix: build_freshness must NOT store `stale`,
    `age_days`, or an `alarms` list — those flip with wall-clock and would make
    a committed freshness.json spuriously drift. Staleness is derived at render.
    """
    gate = _load_gate()
    old = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "co-snap.json").write_text(
        json.dumps(
            {
                "suite": "co-snap-ecps",
                "provenance": {"generated_at": old, "run_kind": "weekly"},
            }
        )
    )
    (data_dir / "coverage_overview.json").write_text(
        json.dumps(
            {
                "axiom": {
                    "programs": [
                        {
                            "program": "snap",
                            "jurisdiction": "CO",
                            "status": "executable",
                        }
                    ]
                }
            }
        )
    )
    monkeypatch.setattr(gate, "DASHBOARD_DATA_DIR", data_dir)
    monkeypatch.setattr(gate, "COVERAGE_OVERVIEW", data_dir / "coverage_overview.json")
    monkeypatch.setattr(gate, "AFFECTED_MAP", tmp_path / "no-map.json")
    fresh = gate.build_freshness()
    assert "alarms" not in fresh
    assert all("stale" not in s and "age_days" not in s for s in fresh["suites"])
    # But the invariant facts ARE present: the executable surface is linked to
    # its matching report suite so the dashboard can derive the alarm.
    surface = next(s for s in fresh["executable_surfaces"] if s["program"] == "snap")
    assert "co-snap-ecps" in surface["suites"]
    suite_entry = next(s for s in fresh["suites"] if s["suite"] == "co-snap-ecps")
    assert suite_entry["generated_at"] == old


def test_write_freshness_is_idempotent_when_comparable_equal(monkeypatch, tmp_path):
    """A regeneration with no comparable change must keep the committed file
    byte-for-byte (its doc-level generated_at included) — otherwise every
    6-hourly affected rerun would churn a timestamp-only diff into a commit.
    """
    gate = _load_gate()
    out = tmp_path / "freshness.json"
    monkeypatch.setattr(gate, "FRESHNESS_OUTPUT", out)
    committed = {
        "generated_at": "2026-01-01T00:00:00Z",
        "suites": [{"suite": "s", "generated_at": "2026-05-01T00:00:00Z"}],
    }
    out.write_text(json.dumps(committed, indent=2) + "\n")
    before = out.read_text()

    regenerated = {**committed, "generated_at": "2026-02-02T00:00:00Z"}
    gate._write_freshness(regenerated)
    assert out.read_text() == before  # untouched, stamp preserved


def test_write_freshness_rewrites_on_comparable_change(monkeypatch, tmp_path):
    """NEGATIVE: a report-fact change (per-suite generated_at) must rewrite the
    file — idempotency must not become staleness."""
    gate = _load_gate()
    out = tmp_path / "freshness.json"
    monkeypatch.setattr(gate, "FRESHNESS_OUTPUT", out)
    out.write_text(
        json.dumps(
            {
                "generated_at": "2026-01-01T00:00:00Z",
                "suites": [{"suite": "s", "generated_at": "2026-05-01T00:00:00Z"}],
            }
        )
        + "\n"
    )
    rerun = {
        "generated_at": "2026-02-02T00:00:00Z",
        "suites": [{"suite": "s", "generated_at": "2026-06-01T00:00:00Z"}],
    }
    gate._write_freshness(rerun)
    assert json.loads(out.read_text()) == rerun


def test_build_freshness_surfaces_reemission_status(monkeypatch, tmp_path):
    """A skip-capable lane that re-emits the committed report stamps
    `reemitted_report` (+ the source stamp dating the actual numbers) into
    provenance; freshness must CARRY both — an entry showing only the
    re-emission's generated_at presents permanently re-emitted numbers as
    freshly run (sol stack review F6). A genuinely fresh run must read
    reemitted=false."""
    gate = _load_gate()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    source = {"path": "reports/x-2026-07-01.json", "generated_at": "2026-07-01T00:00:00Z"}
    (data_dir / "reemitted.json").write_text(
        json.dumps(
            {
                "suite": "reemit-suite",
                "provenance": {
                    "generated_at": "2026-08-02T00:00:00Z",
                    "run_kind": "weekly",
                    "reemitted_report": True,
                    "reemitted_from": source,
                },
            }
        )
    )
    (data_dir / "fresh.json").write_text(
        json.dumps(
            {
                "suite": "fresh-suite",
                "provenance": {
                    "generated_at": "2026-08-02T00:00:00Z",
                    "run_kind": "manual",
                },
            }
        )
    )
    (data_dir / "coverage_overview.json").write_text(
        json.dumps({"axiom": {"programs": []}})
    )
    monkeypatch.setattr(gate, "DASHBOARD_DATA_DIR", data_dir)
    monkeypatch.setattr(gate, "COVERAGE_OVERVIEW", data_dir / "coverage_overview.json")
    monkeypatch.setattr(gate, "AFFECTED_MAP", tmp_path / "no-map.json")

    fresh = gate.build_freshness()
    reemitted = next(s for s in fresh["suites"] if s["suite"] == "reemit-suite")
    assert reemitted["reemitted"] is True
    assert reemitted["reemitted_from"] == source
    genuinely_fresh = next(s for s in fresh["suites"] if s["suite"] == "fresh-suite")
    assert genuinely_fresh["reemitted"] is False
    assert genuinely_fresh["reemitted_from"] is None
