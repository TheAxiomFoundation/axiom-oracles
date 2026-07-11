"""Tests for the canonical RuleSpec checkout hard cut."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from axiom_oracles.bridges.repo_routing import (
    candidate_jurisdiction_content_dirs,
    canonical_rulespec_checkout_name,
    canonical_rulespec_module_path,
    canonical_rulespec_repo_name,
    canonical_rulespec_root_identity,
    find_policy_repo_root,
    is_policy_repo_root,
    iter_jurisdiction_content_dirs,
    jurisdiction_subdir_names,
)
from axiom_oracles.bridges.rulespec_paths import (
    require_axiom_binary,
    require_axiom_compiled_artifact,
    require_rulespec_checkout,
    require_rulespec_module,
    resolve_rulespec_module_ref,
    resolve_rulespec_program,
    rulespec_engine_env,
    rulespec_root_args,
)


def _init_checkout(path: Path, origin: str) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", origin],
        cwd=path,
        check=True,
        capture_output=True,
    )


def test_exact_country_checkout_and_jurisdiction_root_are_canonical(tmp_path):
    checkout = tmp_path / "rulespec-us"
    _init_checkout(checkout, "https://github.com/TheAxiomFoundation/rulespec-us.git")
    content_root = checkout / "us-co"
    content_root.mkdir()

    assert is_policy_repo_root(checkout)
    assert canonical_rulespec_repo_name(checkout) == "rulespec-us"
    assert canonical_rulespec_repo_name(content_root) == "rulespec-us"
    assert canonical_rulespec_root_identity(content_root) == "rulespec-us/us-co"
    assert candidate_jurisdiction_content_dirs(checkout, "us-co") == [content_root]
    assert candidate_jurisdiction_content_dirs(content_root, "us-co") == [content_root]
    assert iter_jurisdiction_content_dirs(checkout) == [("us-co", content_root)]
    assert iter_jurisdiction_content_dirs(content_root) == [("us-co", content_root)]


@pytest.mark.parametrize(
    "invalid_root",
    ["rulespec-us-co", "workspace", "rulespec-us-clean.abcd"],
)
def test_flat_workspace_and_aliased_roots_are_rejected(tmp_path, invalid_root):
    root = tmp_path / invalid_root
    root.mkdir()
    if invalid_root == "rulespec-us-clean.abcd":
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "https://github.com/TheAxiomFoundation/rulespec-us.git",
            ],
            cwd=root,
            check=True,
            capture_output=True,
        )
        (root / "us").mkdir()

    assert not is_policy_repo_root(root)
    assert canonical_rulespec_repo_name(root) is None
    assert candidate_jurisdiction_content_dirs(root, "us") == []
    assert iter_jurisdiction_content_dirs(root) == []
    with pytest.raises(ValueError, match="exact canonical"):
        require_rulespec_checkout(root)


def test_git_origin_must_match_exact_checkout_name(tmp_path):
    checkout = tmp_path / "rulespec-us"
    _init_checkout(checkout, "https://example.com/not-rulespec-us.git")
    (checkout / "us").mkdir()

    assert not is_policy_repo_root(checkout)
    assert canonical_rulespec_root_identity(checkout / "us") is None


def test_exact_ssh_git_origin_is_only_verified_not_used_for_aliasing(tmp_path):
    checkout = tmp_path / "rulespec-us"
    _init_checkout(checkout, "git@github.com:TheAxiomFoundation/rulespec-us.git")
    (checkout / "us").mkdir()

    assert is_policy_repo_root(checkout)

    alias = tmp_path / "rulespec-us-clean"
    _init_checkout(alias, "git@github.com:TheAxiomFoundation/rulespec-us.git")
    (alias / "us").mkdir()
    assert not is_policy_repo_root(alias)


def test_checkout_with_nested_same_name_symlink_is_rejected(tmp_path):
    checkout = tmp_path / "rulespec-us"
    checkout.mkdir()
    target = tmp_path / "legacy-rulespec-us"
    target.mkdir()
    (checkout / "rulespec-us").symlink_to(target, target_is_directory=True)

    assert canonical_rulespec_checkout_name(checkout) is None


def test_workspace_and_axiom_nesting_are_not_discovered(tmp_path):
    checkout = tmp_path / "workspace" / "_axiom" / "rulespec-us"
    (checkout / "us").mkdir(parents=True)

    assert iter_jurisdiction_content_dirs(tmp_path / "workspace") == []
    assert candidate_jurisdiction_content_dirs(tmp_path / "workspace", "us") == []


def test_symlinked_checkout_and_content_roots_are_rejected(tmp_path):
    real_checkout = tmp_path / "real" / "rulespec-us"
    (real_checkout / "us-co").mkdir(parents=True)
    checkout_alias = tmp_path / "alias" / "rulespec-us"
    checkout_alias.parent.mkdir()
    checkout_alias.symlink_to(real_checkout, target_is_directory=True)
    external = tmp_path / "external-us-ny"
    external.mkdir()
    (real_checkout / "us-ny").symlink_to(external, target_is_directory=True)

    assert candidate_jurisdiction_content_dirs(checkout_alias, "us-co") == []
    assert canonical_rulespec_root_identity(real_checkout / "us-ny") is None
    assert "us-ny" not in jurisdiction_subdir_names(real_checkout)


@pytest.mark.parametrize("suffix", [".yml", ".json"])
def test_compile_path_rejects_non_yaml_suffix(tmp_path, suffix):
    checkout = tmp_path / "rulespec-us"
    content_root = checkout / "us"
    program = content_root / "statutes" / "26" / f"24{suffix}"
    program.parent.mkdir(parents=True)
    program.write_text("format: rulespec/v1\nrules: []\n")

    assert canonical_rulespec_module_path(program, content_root=content_root) is None
    with pytest.raises(ValueError, match="exact .yaml"):
        require_rulespec_module(program, checkout)


def test_compile_path_rejects_noncanonical_top_level_directory(tmp_path):
    checkout = tmp_path / "rulespec-us"
    content_root = checkout / "us"
    program = content_root / "misc" / "24.yaml"
    program.parent.mkdir(parents=True)
    program.write_text("format: rulespec/v1\nrules: []\n")

    with pytest.raises(ValueError, match="four atomic roots"):
        require_rulespec_module(program, checkout)


def test_compile_path_preserves_exact_canonical_path(tmp_path):
    checkout = tmp_path / "rulespec-us"
    content_root = checkout / "us"
    program = content_root / "statutes" / "26" / "24.yaml"
    program.parent.mkdir(parents=True)
    program.write_text("format: rulespec/v1\nrules: []\n")

    assert require_rulespec_module(program, checkout) == program.resolve()
    assert find_policy_repo_root(program) == content_root


def test_program_override_rejects_symlinked_module(tmp_path):
    checkout = tmp_path / "rulespec-us"
    content_root = checkout / "us"
    program = content_root / "statutes" / "26" / "24.yaml"
    program.parent.mkdir(parents=True)
    program.write_text("format: rulespec/v1\nrules: []\n")
    alias = program.with_name("24-alias.yaml")
    alias.symlink_to(program)

    with pytest.raises(ValueError, match="exact .yaml"):
        resolve_rulespec_program(
            checkout,
            jurisdiction="us",
            relative_path=Path("statutes/26/24.yaml"),
            override=alias,
        )


def test_absolute_module_ref_resolves_only_canonical_real_yaml(tmp_path):
    checkout = tmp_path / "rulespec-us"
    module = checkout / "us/statutes/26/24.yaml"
    module.parent.mkdir(parents=True)
    module.write_text("format: rulespec/v1\nrules: []\n")

    assert resolve_rulespec_module_ref(checkout, "us:statutes/26/24") == (
        module.resolve()
    )
    with pytest.raises(ValueError, match="canonical RuleSpec module reference"):
        resolve_rulespec_module_ref(checkout, "us:statutes/26/24.yaml")

    module.unlink()
    real_module = tmp_path / "real-24.yaml"
    real_module.write_text("format: rulespec/v1\nrules: []\n")
    module.symlink_to(real_module)
    with pytest.raises(ValueError, match="exact .yaml"):
        resolve_rulespec_module_ref(checkout, "us:statutes/26/24")


def test_engine_env_scrubs_ambient_roots_and_uses_explicit_args(monkeypatch, tmp_path):
    checkout = tmp_path / "rulespec-us"
    (checkout / "us").mkdir(parents=True)
    monkeypatch.setenv("AXIOM_RULESPEC_REPO_ROOTS", "/ambient:/workspace")
    monkeypatch.delenv("AXIOM_RULESPEC_REPO_ROOTS_EXCLUSIVE", raising=False)

    env = rulespec_engine_env()

    assert "AXIOM_RULESPEC_REPO_ROOTS" not in env
    assert "AXIOM_RULESPEC_REPO_ROOTS_EXCLUSIVE" not in env
    assert rulespec_root_args(checkout) == [
        "--rulespec-root",
        str(checkout.resolve()),
    ]


def test_binary_must_be_explicit_real_executable(tmp_path):
    binary = tmp_path / "axiom-rules-engine"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    alias = tmp_path / "binary-alias"
    alias.symlink_to(binary)

    assert require_axiom_binary(binary) == binary.resolve()
    with pytest.raises(ValueError, match="symlinked"):
        require_axiom_binary(alias)


def test_compiled_artifact_must_be_explicit_real_file(tmp_path):
    artifact = tmp_path / "program.compiled.json"
    artifact.write_text("{}\n")
    alias = tmp_path / "artifact-alias.json"
    alias.symlink_to(artifact)

    assert require_axiom_compiled_artifact(artifact) == artifact.resolve()
    with pytest.raises(ValueError, match="symlinked"):
        require_axiom_compiled_artifact(alias)


def test_darwin_tmp_alias_is_not_treated_as_user_symlink(tmp_path):
    checkout = tmp_path / "rulespec-us"
    (checkout / "us").mkdir(parents=True)
    expected = os.path.abspath(checkout)

    assert str(require_rulespec_checkout(checkout)) == str(Path(expected).resolve())
