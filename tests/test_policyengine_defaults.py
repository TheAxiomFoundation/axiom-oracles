"""Default updates reach executions without migrating explicit suite vintages."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from axiom_oracles import policyengine_defaults as defaults


INITIAL_PACKAGES = {
    "policyengine": "4.18.9",
    "policyengine-us": "1.752.2",
    "policyengine-core": "3.28.0",
    "spm-calculator": "0.3.1",
}
CANDIDATE_PACKAGES = {
    "policyengine": "6.11.1",
    "policyengine-us": "2.68.0",
    "policyengine-core": "3.30.3",
    "spm-calculator": "1.0.0.post1",
}
ROOT = Path(__file__).resolve().parents[1]


def _document(packages=None):
    return {"schema": 1, "packages": dict(packages or INITIAL_PACKAGES)}


def _requirements(packages=None):
    return "\n".join(
        f"{name}=={version} \\\n    --hash=sha256:{'a' * 64}"
        for name, version in (packages or CANDIDATE_PACKAGES).items()
    ) + "\n"


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate_runner(monkeypatch, tmp_path):
    manifest = tmp_path / "defaults.json"
    manifest.write_text(json.dumps(_document(CANDIDATE_PACKAGES)))
    monkeypatch.setattr(defaults, "DEFAULTS_PATH", manifest)
    runner = _load_script("run_comparison")
    monkeypatch.setattr(runner, "DEFAULT_REQUIREMENTS_PATH", tmp_path / "absent-lock.txt")
    return runner


def test_initial_manifest_preserves_the_existing_default_stack(monkeypatch, tmp_path):
    manifest = tmp_path / "defaults.json"
    manifest.write_text(json.dumps(_document()))
    monkeypatch.setattr(defaults, "DEFAULTS_PATH", manifest)
    assert defaults.load_defaults() == INITIAL_PACKAGES
    runner = _load_script("run_comparison")
    assert runner._resolve_pe_oracle_pins({}) == (
        "policyengine==4.18.9",
        "policyengine-us==1.752.2",
        "policyengine-core==3.28.0",
    )


@pytest.mark.parametrize(
    "version",
    ["", "latest", ">=1.0", "1.0.0rc1", "1.0.dev1", "1.0+local", "v1.0", True, 1],
)
def test_manifest_rejects_non_exact_or_unstable_versions(version):
    document = _document()
    document["packages"]["policyengine-us"] = version
    with pytest.raises(ValueError, match="exact stable version"):
        defaults.validate_defaults(document)


def test_manifest_accepts_stable_post_releases():
    assert defaults.validate_defaults(_document(CANDIDATE_PACKAGES)) == CANDIDATE_PACKAGES


@pytest.mark.parametrize("field,value", [("schema", True), ("schema", 2), ("schema", "1")])
def test_manifest_requires_its_exact_schema(field, value):
    document = _document()
    document[field] = value
    with pytest.raises(ValueError, match="schema must be 1"):
        defaults.validate_defaults(document)


def test_manifest_rejects_missing_and_unknown_fields():
    documents = [_document(), _document(), _document()]
    documents[0]["extra"] = "unexpected"
    documents[1]["packages"].pop("policyengine-core")
    documents[2]["packages"]["unknown-package"] = "1.0.0"
    for document in documents:
        with pytest.raises(ValueError, match="exactly"):
            defaults.validate_defaults(document)


def test_manifest_rejects_duplicate_json_fields(tmp_path):
    manifest = tmp_path / "defaults.json"
    manifest.write_text('{"schema":1,"schema":1,"packages":{}}')
    with pytest.raises(ValueError, match="duplicate manifest field"):
        defaults.load_defaults(manifest)


def test_missing_manifest_fails_instead_of_falling_back(tmp_path):
    with pytest.raises(ValueError, match="missing.json"):
        defaults.load_defaults(tmp_path / "missing.json")


def test_candidate_manifest_controls_default_execution_and_provenance(monkeypatch, tmp_path):
    runner = _candidate_runner(monkeypatch, tmp_path)
    monkeypatch.setattr(runner.pinned_artifacts, "with_args", lambda pins: list(pins))
    pins = defaults.pe_pins(CANDIDATE_PACKAGES)
    assert runner._resolve_pe_oracle_pins({}) == pins
    assert runner._pe_oracle_with_args(pins) == [
        *pins,
        "spm-calculator==1.0.0.post1",
    ]
    output = tmp_path / "report.json"
    output.write_text('{"suite":"defaults-test","engines":{"left":"taxcalc","right":"policyengine"}}')
    config = {
        "name": "defaults-test",
        "runner": {"parameters": {"left": "taxcalc", "right": "policyengine"}},
    }
    oracle = runner._build_run_provenance(config, "axiom-oracles-compare", output)["oracle"]
    assert oracle["policyengine_package"] == pins[0]
    assert oracle["policyengine_us"] == CANDIDATE_PACKAGES["policyengine-us"]
    assert oracle["policyengine_core"] == CANDIDATE_PACKAGES["policyengine-core"]


def test_explicit_historical_stack_keeps_its_companion_after_default_update(
    monkeypatch, tmp_path
):
    runner = _candidate_runner(monkeypatch, tmp_path)
    monkeypatch.setattr(runner.pinned_artifacts, "with_args", lambda pins: list(pins))
    params = {
        "policyengine_version": "4.18.9",
        "policyengine_us_version": "1.767.3",
        "policyengine_core_version": "3.30.3",
    }
    before = copy.deepcopy(params)
    pins = runner._resolve_pe_oracle_pins(params)
    assert pins == (
        "policyengine==4.18.9",
        "policyengine-us==1.767.3",
        "policyengine-core==3.30.3",
    )
    assert runner._pe_oracle_with_args(pins) == [*pins, "spm-calculator==0.3.1"]
    assert params == before
    assert runner._pe_oracle_with_args(("policyengine-us==1.705.1",))[-1] == (
        "spm-calculator==0.3.1"
    )


@pytest.mark.parametrize(
    "params",
    [
        {"policyengine_us_version": "1.767.3"},
        {"policyengine_version": "4.18.9"},
        {"policyengine_core_version": "3.30.3"},
        {"policyengine_version": "4.18.9", "policyengine_us_version": "1.767.3"},
    ],
)
def test_partial_us_override_cannot_mix_historical_and_updated_defaults(
    monkeypatch, tmp_path, params
):
    runner = _candidate_runner(monkeypatch, tmp_path)
    with pytest.raises(SystemExit, match="together"):
        runner._resolve_pe_oracle_pins(params)


def test_artifact_inventory_names_the_manifest_source():
    checker = _load_script("check_pinned_artifacts")
    pins, _ = checker.inventory()
    for name, version in defaults.load_defaults().items():
        assert checker.Use("data/policyengine_defaults.json") in pins[(name, version)]


def test_runtime_probe_bootstrap_is_shared_with_the_comparison_cli():
    runner = _load_script("run_comparison")
    bootstrap = runner._PE_RUNTIME_BOOTSTRAP
    assert bootstrap.strip()
    assert "_runtime_engine_versions" in bootstrap
    assert "POLICYENGINE_SKIP_COUNTRY_IMPORTS" in bootstrap
    assert "from axiom_oracles.cli import cli" not in bootstrap
    assert runner._PE_CERT_OVERRIDE.startswith(bootstrap)
    compile(bootstrap, "<policyengine-runtime-bootstrap>", "exec")


def test_valid_default_lock_is_passed_to_the_actual_runtime(monkeypatch, tmp_path):
    runner = _candidate_runner(monkeypatch, tmp_path)
    lock = tmp_path / "requirements.txt"
    lock.write_text(_requirements() + f"packaging==26.2 --hash=sha256:{'b' * 64}\n")
    monkeypatch.setattr(runner, "DEFAULT_REQUIREMENTS_PATH", lock)
    monkeypatch.setattr(runner.pinned_artifacts, "with_args", lambda pins: list(pins))
    pins = runner._resolve_pe_oracle_pins({})
    assert runner._pe_oracle_with_args(pins) == [
        "--with-requirements", str(lock), *pins, "spm-calculator==1.0.0.post1"
    ]


def test_default_lock_must_match_manifest_before_runtime_install(monkeypatch, tmp_path):
    runner = _candidate_runner(monkeypatch, tmp_path)
    lock = tmp_path / "requirements.txt"
    lock.write_text(_requirements(INITIAL_PACKAGES))
    monkeypatch.setattr(runner, "DEFAULT_REQUIREMENTS_PATH", lock)
    with pytest.raises(ValueError, match="does not match the manifest"):
        runner._pe_oracle_with_args(runner._resolve_pe_oracle_pins({}))


def test_historical_stack_does_not_read_default_lock(monkeypatch, tmp_path):
    runner = _candidate_runner(monkeypatch, tmp_path)
    lock = tmp_path / "requirements.txt"
    lock.write_text("invalid default lock must not affect a historical suite")
    monkeypatch.setattr(runner, "DEFAULT_REQUIREMENTS_PATH", lock)
    monkeypatch.setattr(runner.pinned_artifacts, "with_args", lambda pins: list(pins))
    historical = defaults.pe_pins(INITIAL_PACKAGES)
    assert runner._pe_oracle_with_args(historical) == [
        *historical, "spm-calculator==0.3.1"
    ]


@pytest.mark.parametrize(
    "extra",
    [
        "unhashed==1.0",
        f"loose>=1.0 --hash=sha256:{'a' * 64}",
        f"wildcard==1.* --hash=sha256:{'a' * 64}",
        f"remote @ https://example.org/package.whl --hash=sha256:{'a' * 64}",
        f"marked==1.0; sys_platform == 'other' --hash=sha256:{'a' * 64}",
        f"extra[thing]==1.0 --hash=sha256:{'a' * 64}",
        "--index-url https://example.org/simple",
        "-e ./somewhere",
        f"preview==1.0rc1 --hash=sha256:{'a' * 64}",
        f"local==1.0+local --hash=sha256:{'a' * 64}",
        f"policyengine_us==2.68.0 --hash=sha256:{'a' * 64}",
    ],
)
def test_default_lock_rejects_options_urls_unhashed_or_ambiguous_requirements(extra):
    with pytest.raises(ValueError):
        defaults.validate_requirements_lock(_requirements() + extra + "\n", CANDIDATE_PACKAGES)


def test_default_lock_requires_every_profile_package():
    packages = dict(CANDIDATE_PACKAGES)
    packages.pop("policyengine-core")
    with pytest.raises(ValueError, match="does not match the manifest"):
        defaults.validate_requirements_lock(_requirements(packages), CANDIDATE_PACKAGES)
