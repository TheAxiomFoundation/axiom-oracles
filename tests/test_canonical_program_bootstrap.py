from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).parents[1]
COMPARISONS_DIR = REPO_ROOT / "comparisons"
MANIFEST_PATH = REPO_ROOT / "docs/canonical-rulespec-program-bootstrap.json"
CANONICAL_PREFIX = "$HOME/TheAxiomFoundation/rulespec-us/"
CANONICAL_BINARY = (
    "$HOME/TheAxiomFoundation/axiom-rules-engine/target/release/axiom-rules-engine"
)
CANONICAL_COMPOSER = "$HOME/TheAxiomFoundation/axiom-compose/.venv/bin/axiom-compose"
LEGACY_ROUTING_KEYS = {
    "rulespec_roots",
    "rulespec_remote",
    "axiom_rulespec_repo_roots",
    "axiom_rules_repo",
}
AXIOM_RUNTIME_KEYS = {
    "rulespec_root",
    "axiom_binary",
    "axiom_program",
    "axiom_compose_binary",
    "axiom_composed_program",
    "axiom_compiled_program",
}


def _configured_programs() -> dict[str, str]:
    configured: dict[str, str] = {}
    for path in sorted(COMPARISONS_DIR.glob("*.yaml")):
        config = yaml.safe_load(path.read_text()) or {}
        runner = config.get("runner") or {}
        parameters = runner.get("parameters") or {}
        raw = runner.get("axiom_program") or parameters.get("axiom_program")
        if raw is None:
            continue
        assert raw.startswith(CANONICAL_PREFIX), (
            f"{path.name} must name a program inside the exact rulespec-us checkout"
        )
        configured[path.stem] = raw.removeprefix(CANONICAL_PREFIX)
    return configured


def test_program_bootstrap_manifest_covers_every_explicit_program_config() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())
    assert manifest["schema"] == (
        "axiom-oracles/canonical-rulespec-program-bootstrap/v1"
    )

    configured = _configured_programs()
    manifested: dict[str, str] = {}
    for entry in manifest["files"]:
        destination = entry["destination"]
        assert re.fullmatch(
            r"us(?:-[a-z0-9]+)*/programs/.+\.yaml",
            destination,
        )
        assert re.fullmatch(r"[0-9a-f]{64}", entry["source"]["sha256"])
        for suite in entry["affected_comparisons"]:
            assert suite not in manifested
            manifested[suite] = destination

    assert manifested == configured


def test_oracles_repo_no_longer_owns_rulespec_program_yaml() -> None:
    assert not list((REPO_ROOT / "programs").rglob("*.yaml"))


def test_every_registry_axiom_lane_declares_one_exact_runtime() -> None:
    """Pin the hard cut across every active comparison registry entry."""

    root_pattern = re.compile(r"\$HOME/TheAxiomFoundation/rulespec-(us|uk|be)")
    module_pattern = re.compile(
        r"\$HOME/TheAxiomFoundation/rulespec-(us|uk|be)/"
        r"(?:us|uk|be)(?:-[a-z0-9]+)?/"
        r"programs/.+\.yaml"
    )
    output_pattern = re.compile(r"/tmp/axiom-composed/[a-z0-9-]+\.yaml")

    for path in sorted(COMPARISONS_DIR.glob("*.yaml")):
        if path.name.endswith(".fixtures.yaml"):
            continue
        config = yaml.safe_load(path.read_text()) or {}
        runner = config.get("runner")
        if not runner:
            continue
        parameters = runner.get("parameters") or {}
        present_keys = set(runner) | set(parameters)
        assert not present_keys & LEGACY_ROUTING_KEYS, path.name

        uses_axiom = runner.get("type") != "axiom-oracles-compare" or "axiom" in {
            parameters.get("left"),
            parameters.get("right"),
        }
        roots = [
            section["rulespec_root"]
            for section in (runner, parameters)
            if "rulespec_root" in section
        ]
        binaries = [
            section["axiom_binary"]
            for section in (runner, parameters)
            if "axiom_binary" in section
        ]
        if not uses_axiom:
            assert not present_keys & AXIOM_RUNTIME_KEYS, path.name
            continue

        assert len(roots) == 1 and root_pattern.fullmatch(roots[0]), path.name
        assert binaries == [CANONICAL_BINARY], path.name

        program = parameters.get("axiom_program")
        if program is None:
            continue
        assert module_pattern.fullmatch(program), path.name
        assert parameters.get("axiom_compose_binary") == CANONICAL_COMPOSER, path.name
        assert output_pattern.fullmatch(parameters.get("axiom_composed_program", "")), (
            path.name
        )
        assert re.fullmatch(
            r"/tmp/[a-z0-9-]+\.json",
            parameters.get("axiom_compiled_program", ""),
        ), path.name
