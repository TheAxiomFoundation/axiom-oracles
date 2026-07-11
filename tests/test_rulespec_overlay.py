"""Tests for the spec-driven RuleSpec overlay builder."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.rulespec_overlay import (
    OVERLAY_SPEC_SCHEMA_VERSION,
    OverlaySpec,
    ParameterPatch,
    build_overlay,
    load_overlay_spec,
    rewrite_output_ids,
)

MODULE_A = "us/regulations/7-cfr/273/9.yaml"
COMPOSITION = "us-co/policies/cdhs/snap/comp.yaml"
PARAM_FILE = "us-co/regulations/10-ccr-2506-1/4.407.31.yaml"
OTHER_FILE = "us/regulations/7-cfr/273/3.yaml"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fake_rulespec_tree(root: Path, *, param_formula: str = "594") -> None:
    """A miniature rulespec monorepo with fy-2026-cola references."""
    _write(
        root / MODULE_A,
        "imports:\n- us:policies/usda/snap/fy-2026-cola/deductions\n",
    )
    _write(
        root / COMPOSITION,
        "imports:\n"
        "- us:policies/usda/snap/fy-2026-cola/maximum-allotments\n"
        "- us:policies/usda/snap/fy-2026-cola/deductions\n",
    )
    _write(
        root / PARAM_FILE,
        yaml.safe_dump(
            {
                "rules": [
                    {
                        "name": "colorado_snap_heating_cooling_utility_allowance_amount",
                        "kind": "parameter",
                        "versions": [
                            {"effective_from": "2025-10-01", "formula": param_formula}
                        ],
                    }
                ]
            },
            sort_keys=False,
        ),
    )
    _write(root / OTHER_FILE, "imports:\n- us:regulations/7-cfr/273/2\n")


def _spec(**overrides) -> OverlaySpec:
    base = {
        "name": "fake-overlay",
        "program": COMPOSITION,
        "notes": "",
        "module_id_rewrites": {"fy-2026-cola": "fy-2024-cola"},
        "rewrite_files": (MODULE_A, COMPOSITION),
        "parameter_patches": (
            ParameterPatch(
                file=PARAM_FILE,
                rule="colorado_snap_heating_cooling_utility_allowance_amount",
                from_value="594",
                to_value="560",
                source="cite/page-183",
            ),
        ),
    }
    base.update(overrides)
    return OverlaySpec(**base)


def test_build_overlay_rewrites_patches_and_records_provenance(tmp_path: Path) -> None:
    root = tmp_path / "rulespec-us"
    _fake_rulespec_tree(root)
    build = build_overlay(_spec(), root, tmp_path / "dest")

    # Overlay root reuses the monorepo basename so prefix resolution matches.
    assert build.overlay_root.name == "rulespec-us"
    assert build.program_path == build.overlay_root / COMPOSITION

    module_text = (build.overlay_root / MODULE_A).read_text()
    assert "fy-2024-cola" in module_text
    assert "fy-2026-cola" not in module_text
    composition_text = build.program_path.read_text()
    assert "fy-2026-cola" not in composition_text

    patched = yaml.safe_load((build.overlay_root / PARAM_FILE).read_text())
    assert patched["rules"][0]["versions"][0]["formula"] == "560"

    provenance = build.provenance
    assert provenance["overlay"] == "fake-overlay"
    assert provenance["schema"] == OVERLAY_SPEC_SCHEMA_VERSION
    assert provenance["rewrite_counts"][MODULE_A] == 1
    assert provenance["rewrite_counts"][COMPOSITION] == 2
    assert provenance["patches"] == [
        {
            "file": PARAM_FILE,
            "rule": "colorado_snap_heating_cooling_utility_allowance_amount",
            "from": "594",
            "to": "560",
            "source": "cite/page-183",
        }
    ]
    assert set(provenance["file_sha256"]) == {MODULE_A, COMPOSITION, PARAM_FILE}
    assert all(len(digest) == 64 for digest in provenance["file_sha256"].values())


def test_build_overlay_raises_when_patch_from_value_drifted(tmp_path: Path) -> None:
    root = tmp_path / "rulespec-us"
    _fake_rulespec_tree(root, param_formula="999")
    with pytest.raises(ValueError, match="expected '594'"):
        build_overlay(_spec(), root, tmp_path / "dest")


def test_build_overlay_raises_when_rewrite_matches_nothing(tmp_path: Path) -> None:
    root = tmp_path / "rulespec-us"
    _fake_rulespec_tree(root)
    spec = _spec(rewrite_files=(MODULE_A, COMPOSITION, OTHER_FILE))
    with pytest.raises(ValueError, match="no module-id rewrites matched"):
        build_overlay(spec, root, tmp_path / "dest")


def test_build_overlay_rejects_flat_checkout(tmp_path: Path) -> None:
    root = tmp_path / "rulespec-us-co"
    _fake_rulespec_tree(root)

    with pytest.raises(ValueError, match="exact canonical rulespec-<country>"):
        build_overlay(_spec(), root, tmp_path / "dest")


def test_build_overlay_rejects_partial_layout_path(tmp_path: Path) -> None:
    root = tmp_path / "rulespec-us"
    _fake_rulespec_tree(root)
    spec = _spec(program="us-co/snap.yaml")

    with pytest.raises(ValueError, match="canonical <jurisdiction>/<content-root>"):
        build_overlay(spec, root, tmp_path / "dest")


def test_build_overlay_rejects_yml_content(tmp_path: Path) -> None:
    root = tmp_path / "rulespec-us"
    _fake_rulespec_tree(root)
    _write(root / "us-co/policies/legacy.yml", "rules: []\n")

    with pytest.raises(ValueError, match=r"legacy \.yml"):
        build_overlay(_spec(), root, tmp_path / "dest")


def test_build_overlay_rejects_symlinked_content(tmp_path: Path) -> None:
    root = tmp_path / "rulespec-us"
    _fake_rulespec_tree(root)
    target = root / "us-co/policies/target.yaml"
    _write(target, "rules: []\n")
    (root / "us-co/policies/alias.yaml").symlink_to(target)

    with pytest.raises(ValueError, match="symlinked RuleSpec content"):
        build_overlay(_spec(), root, tmp_path / "dest")


def test_rewrite_output_ids_rewrites_only_matching_ids() -> None:
    rewritten = rewrite_output_ids(
        {
            "std": "us:policies/usda/snap/fy-2026-cola/deductions#snap_standard_deduction",
            "allotment": "us-co:regulations/10-ccr-2506-1/4.207.2#snap_allotment",
        },
        {"fy-2026-cola": "fy-2024-cola"},
    )
    assert rewritten["std"] == (
        "us:policies/usda/snap/fy-2024-cola/deductions#snap_standard_deduction"
    )
    assert rewritten["allotment"] == (
        "us-co:regulations/10-ccr-2506-1/4.207.2#snap_allotment"
    )


def test_load_packaged_overlay_spec_is_wellformed() -> None:
    spec = load_overlay_spec("us-co-snap-fy2024")
    assert spec.name == "us-co-snap-fy2024"
    assert spec.program == "us-co/policies/cdhs/snap/fy-2026-benefit-calculation.yaml"
    assert spec.module_id_rewrites == {
        f"us:policies/usda/snap/fy-2026-cola/{module}": (
            f"us:policies/usda/snap/fy-2024-cola/{module}"
        )
        for module in (
            "maximum-allotments",
            "deductions",
            "income-eligibility-standards",
        )
    }
    assert len(spec.rewrite_files) == 16
    assert len(spec.parameter_patches) == 4
    # Each patch cites the FY 2024 technical documentation page.
    assert all(
        "snap-qc-fy2024-technical-documentation/page-183" in patch.source
        for patch in spec.parameter_patches
    )
    amounts = {(patch.from_value, patch.to_value) for patch in spec.parameter_patches}
    assert amounts == {("594", "560"), ("377", "356"), ("71", "67"), ("97", "91")}
    # Notes cite the retiring inversion issue and the EUROMOD precedent.
    assert "759" in spec.notes
    assert "euromod" in spec.notes.lower()


def test_load_overlay_spec_rejects_wrong_schema(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump({"schema": "nope", "name": "x"}))
    with pytest.raises(ValueError, match="expected"):
        load_overlay_spec(path)
