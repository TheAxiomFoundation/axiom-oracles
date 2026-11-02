"""Tests for the spec-driven RuleSpec overlay builder."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.rulespec_overlay import (
    OVERLAY_SPEC_SCHEMA_VERSION,
    OverlayDriftError,
    OverlaySpec,
    ParameterPatch,
    build_overlay,
    find_unrewritten_importers,
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


# --------------------------------------------------------------------------- #
# Import-closure drift guard
# --------------------------------------------------------------------------- #

_OLD_DEDUCTIONS = "us:policies/usda/snap/fy-2026-cola/deductions"
_OLD_LIMITS = "us:policies/usda/snap/fy-2026-cola/income-eligibility-standards"
_FULL_ID_REWRITES = {
    old: old.replace("fy-2026-cola", "fy-2024-cola")
    for old in (_OLD_DEDUCTIONS, _OLD_LIMITS)
}
CLOSURE_PROGRAM = "us-ca/policies/cdss/snap/fy-2026-benefit-calculation.yaml"
CLOSURE_FEDERAL = "us/policies/usda/snap/state-plan-composition.yaml"
CLOSURE_MCE = "us-ca/policies/cdss/snap/modified-categorical-eligibility.yaml"
CLOSURE_SUA = "us-ca/policies/cdss/snap/standard-utility-allowance.yaml"
CLOSURE_REG = "us/regulations/7-cfr/273/10.yaml"


def _closure_tree(root: Path) -> None:
    """A miniature monorepo shaped like California's closure on rulespec-us
    main after rulespec-us#1176: the composition imports the federal module
    and a state module (MCE) that imports an fy-2026-cola module directly,
    plus a relative import and a ``#fragment`` import to exercise resolution.
    """
    for vintage in ("fy-2026-cola", "fy-2024-cola"):
        for module in ("deductions", "income-eligibility-standards"):
            _write(
                root / f"us/policies/usda/snap/{vintage}/{module}.yaml",
                "rules: []\n",
            )
    _write(
        root / CLOSURE_PROGRAM,
        "imports:\n"
        "- us:policies/usda/snap/state-plan-composition\n"
        "- us-ca:policies/cdss/snap/modified-categorical-eligibility\n"
        "- ./standard-utility-allowance.yaml\n",
    )
    _write(
        root / CLOSURE_FEDERAL,
        "imports:\n"
        f"- {_OLD_DEDUCTIONS}\n"
        f"- {_OLD_LIMITS}\n"
        "- 'us:regulations/7-cfr/273/10#snap_net_monthly_income'\n",
    )
    _write(
        root / CLOSURE_MCE,
        "imports:\n"
        f"- {_OLD_LIMITS}\n"
        "- us:policies/usda/snap/state-plan-composition\n",
    )
    _write(root / CLOSURE_SUA, "rules: []\n")
    _write(root / CLOSURE_REG, f"imports:\n- {_OLD_DEDUCTIONS}\n")
    # Outside the closure: an unrelated importer must never be flagged.
    _write(
        root / "us-ca/policies/cdss/unrelated.yaml",
        f"imports:\n- {_OLD_DEDUCTIONS}\n",
    )


def _closure_spec(rewrite_files: tuple[str, ...]) -> OverlaySpec:
    return OverlaySpec(
        name="closure-overlay",
        program=CLOSURE_PROGRAM,
        notes="",
        module_id_rewrites=dict(_FULL_ID_REWRITES),
        rewrite_files=rewrite_files,
        parameter_patches=(),
    )


def test_build_overlay_passes_when_every_closure_importer_is_rewritten(
    tmp_path: Path,
) -> None:
    root = tmp_path / "rulespec-us"
    _closure_tree(root)
    spec = _closure_spec((CLOSURE_FEDERAL, CLOSURE_REG, CLOSURE_MCE))

    build = build_overlay(spec, root, tmp_path / "dest")

    assert find_unrewritten_importers(
        build.overlay_root, spec.program, spec.module_id_rewrites
    ) == {}
    assert "fy-2026-cola" not in (build.overlay_root / CLOSURE_MCE).read_text()
    # The out-of-closure importer is left alone, rewritten or not.
    assert _OLD_DEDUCTIONS in (
        build.overlay_root / "us-ca/policies/cdss/unrelated.yaml"
    ).read_text()


def test_build_overlay_names_every_unrewritten_closure_importer(
    tmp_path: Path,
) -> None:
    root = tmp_path / "rulespec-us"
    _closure_tree(root)
    # The committed CA overlay before this guard: MCE (and here 273.10) left out.
    spec = _closure_spec((CLOSURE_FEDERAL,))

    with pytest.raises(OverlayDriftError) as excinfo:
        build_overlay(spec, root, tmp_path / "dest")

    message = str(excinfo.value)
    assert f"{CLOSURE_MCE} imports {_OLD_LIMITS}" in message
    assert f"{CLOSURE_REG} imports {_OLD_DEDUCTIONS}" in message
    assert "2 module(s)" in message
    assert "rewrite_files" in message
    assert "unrelated.yaml" not in message
    # Still a ValueError, so existing stale-overlay handling keeps working.
    assert isinstance(excinfo.value, ValueError)


def test_find_unrewritten_importers_resolves_relative_imports(tmp_path: Path) -> None:
    root = tmp_path / "rulespec-us"
    _closure_tree(root)
    # A relative import names the old vintage without its canonical prefix;
    # resolved from us/regulations/7-cfr/273/ it is the same module id.
    relative_old = "../../../policies/usda/snap/fy-2026-cola/deductions"
    _write(root / CLOSURE_REG, f"imports:\n- {relative_old}\n")
    offenders = find_unrewritten_importers(
        root, CLOSURE_PROGRAM, dict(_FULL_ID_REWRITES)
    )
    assert offenders[CLOSURE_REG] == [relative_old]
    # The composition's own relative import (./standard-utility-allowance.yaml)
    # resolves to a clean module and is not flagged.
    assert CLOSURE_PROGRAM not in offenders
    assert CLOSURE_SUA not in offenders
    assert offenders[CLOSURE_MCE] == [_OLD_LIMITS]
    assert offenders[CLOSURE_FEDERAL] == [_OLD_DEDUCTIONS, _OLD_LIMITS]
    # Every other module in the fixture closure was visited and is clean.
    assert set(offenders) == {CLOSURE_FEDERAL, CLOSURE_MCE, CLOSURE_REG}


def test_find_unrewritten_importers_follows_extends_and_skips_missing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "rulespec-us"
    _write(
        root / "us/program.yaml",
        "extends: base.yaml\nimports:\n- us:does/not/exist\n",
    )
    _write(root / "us/base.yaml", f"imports:\n- {_OLD_DEDUCTIONS}\n")
    offenders = find_unrewritten_importers(
        root, "us/program.yaml", dict(_FULL_ID_REWRITES)
    )
    assert offenders == {"us/base.yaml": [_OLD_DEDUCTIONS]}


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
