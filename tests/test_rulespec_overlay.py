"""Tests for the spec-driven RuleSpec overlay builder."""

from __future__ import annotations

import copy
import os
import tempfile
from datetime import date
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.bridges import rulespec_overlay
from axiom_oracles.bridges.rulespec_overlay import (
    OVERLAY_SPEC_SCHEMA_VERSION,
    OverlayDriftError,
    OverlaySpec,
    ParameterPatch,
    VersionWindowMapping,
    build_overlay,
    find_unrewritten_importers,
    fiscal_year_containing,
    fiscal_year_window,
    load_overlay_spec,
    rewrite_output_ids,
    rules_without_one_version_at,
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


# --------------------------------------------------------------------------- #
# Version-window mapping onto the nominal month
# --------------------------------------------------------------------------- #

_COLA_MODULES = ("maximum-allotments", "deductions", "income-eligibility-standards")
_COLA_REWRITES = {
    f"us:policies/usda/snap/fy-2026-cola/{module}": (
        f"us:policies/usda/snap/fy-2024-cola/{module}"
    )
    for module in _COLA_MODULES
}
WINDOW_PROGRAM = "us-co/policies/cdhs/snap/fy-2026-benefit-calculation.yaml"
WINDOW_CHAIN = "us/regulations/7-cfr/273/10.yaml"
NOMINAL = date(2026, 1, 1)


def _cola_file(module: str, vintage: str = "fy-2024-cola") -> str:
    return f"us/policies/usda/snap/{vintage}/{module}.yaml"


def _cola_rules(module: str, start: str, end: str | None) -> list[dict]:
    """Three rules shaped like the encoded COLA modules: a scalar parameter, a
    household-size table, and a derived formula over them."""

    def version(**body) -> dict:
        window = {"effective_from": start}
        if end is not None:
            window["effective_to"] = end
        return {**window, **body}

    return [
        {
            "name": f"{module}_additional_member",
            "kind": "parameter",
            "dtype": "Money",
            "versions": [version(formula="429")],
        },
        {
            "name": f"{module}_table",
            "kind": "parameter",
            "dtype": "Money",
            "indexed_by": "household_size",
            "versions": [version(values={1: 1215, 2: 1644, 3: 2072})],
        },
        {
            "name": f"{module}_amount",
            "kind": "derived",
            "entity": "Household",
            "versions": [
                version(
                    formula=(
                        f"{module}_table[min(household_size, 3)] + "
                        f"{module}_additional_member * max(household_size - 3, 0)"
                    )
                )
            ],
        },
        {
            # No versions: a source relation carries no window and is left alone.
            "name": f"{module}_restates_memo",
            "kind": "source_relation",
            "source_relation": {"type": "restates", "target": "us:guidance/x"},
        },
    ]


def _window_tree(
    root: Path,
    *,
    windows: dict[str, tuple[str, str | None]],
    chain_start: str = "2025-10-01",
) -> None:
    """A miniature monorepo: a state composition and a federal chain module on
    fy-2026-cola ids, the chain versioned from ``chain_start``, and the three
    fy-2024-cola modules carrying ``windows[module]``."""
    for module in _COLA_MODULES:
        start, end = windows[module]
        _write(
            root / _cola_file(module),
            yaml.safe_dump({"rules": _cola_rules(module, start, end)}, sort_keys=False),
        )
        _write(root / _cola_file(module, "fy-2026-cola"), "rules: []\n")
    _write(
        root / WINDOW_CHAIN,
        yaml.safe_dump(
            {
                "imports": [old for old in _COLA_REWRITES],
                "rules": [
                    {
                        "name": "snap_net_income",
                        "kind": "derived",
                        "versions": [
                            {"effective_from": chain_start, "formula": "1"}
                        ],
                    },
                    {
                        # Superseded and current versions: still one in force.
                        "name": "snap_earned_income_deduction_rate",
                        "kind": "parameter",
                        "versions": [
                            {
                                "effective_from": "0001-01-01",
                                "effective_to": "2008-09-30",
                                "formula": "0.18",
                            },
                            {"effective_from": "2008-10-01", "formula": "0.2"},
                        ],
                    },
                ],
            },
            sort_keys=False,
        ),
    )
    _write(
        root / WINDOW_PROGRAM,
        "imports:\n- us:regulations/7-cfr/273/10\n"
        + "".join(f"- {old}\n" for old in _COLA_REWRITES),
    )


def _window_spec(source_fiscal_year: int = 2024) -> OverlaySpec:
    return OverlaySpec(
        name="window-overlay",
        program=WINDOW_PROGRAM,
        notes="",
        module_id_rewrites=dict(_COLA_REWRITES),
        rewrite_files=(WINDOW_CHAIN, WINDOW_PROGRAM),
        parameter_patches=(),
        version_windows=VersionWindowMapping(source_fiscal_year=source_fiscal_year),
    )


#: rulespec-us main today: only the income module carries effective_to.
_TODAY = {
    "maximum-allotments": ("2023-10-01", None),
    "deductions": ("2023-10-01", None),
    "income-eligibility-standards": ("2023-10-01", "2024-09-30"),
}
#: A later re-encode giving every module the memo's window.
_ALL_CLOSED = {module: ("2023-10-01", "2024-09-30") for module in _COLA_MODULES}


def _without_windows(rules: list[dict]) -> list[dict]:
    stripped = copy.deepcopy(rules)
    for rule in stripped:
        for version in rule.get("versions") or []:
            version.pop("effective_from", None)
            version.pop("effective_to", None)
    return stripped


def _rules(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["rules"]


def test_fiscal_year_helpers() -> None:
    assert fiscal_year_window(2024) == (date(2023, 10, 1), date(2024, 9, 30))
    assert fiscal_year_containing(date(2026, 1, 1)) == 2026
    assert fiscal_year_containing(date(2025, 9, 30)) == 2025
    assert fiscal_year_containing(date(2025, 10, 1)) == 2026


@pytest.mark.parametrize("windows", [_TODAY, _ALL_CLOSED], ids=["today", "all-closed"])
def test_build_overlay_maps_cola_windows_onto_the_nominal_fiscal_year(
    tmp_path: Path, windows: dict
) -> None:
    root = tmp_path / "rulespec-us"
    _window_tree(root, windows=windows)

    build = build_overlay(_window_spec(), root, tmp_path / "dest", nominal_month=NOMINAL)

    # Invariant: every versioned rule in the closure resolves once at 2026-01.
    assert rules_without_one_version_at(build.overlay_root, WINDOW_PROGRAM, NOMINAL) == []
    for module in _COLA_MODULES:
        relative = _cola_file(module)
        source, mapped = _rules(root / relative), _rules(build.overlay_root / relative)
        # Formulas, values, and every other key are exactly as encoded.
        assert _without_windows(mapped) == _without_windows(source)
        for rule in mapped:
            for version in rule.get("versions") or []:
                assert version["effective_from"] == "2025-10-01"
                if windows[module][1] is None:
                    assert "effective_to" not in version
                else:
                    assert version["effective_to"] == "2026-09-30"
        # The source checkout is never mutated through the hardlinked copy.
        assert _rules(root / relative)[0]["versions"][0]["effective_from"] == "2023-10-01"

    record = build.provenance["version_windows"]
    assert record["nominal_month"] == "2026-01-01"
    assert record["source_fiscal_year"] == 2024
    assert record["source_window"] == ["2023-10-01", "2024-09-30"]
    assert record["target_fiscal_year"] == 2026
    assert record["target_window"] == ["2025-10-01", "2026-09-30"]
    assert record["files"] == {
        _cola_file(module): {
            "rules": 3,
            "closed_versions": 3 if windows[module][1] else 0,
            "open_versions": 0 if windows[module][1] else 3,
        }
        for module in _COLA_MODULES
    }
    for module in _COLA_MODULES:
        assert len(build.provenance["file_sha256"][_cola_file(module)]) == 64


_FISCAL_YEARS = st.integers(min_value=1990, max_value=2060)


@settings(max_examples=40, deadline=None)
@given(
    source_fy=_FISCAL_YEARS,
    nominal=st.dates(min_value=date(1990, 1, 1), max_value=date(2060, 9, 30)),
    closed=st.tuples(st.booleans(), st.booleans(), st.booleans()),
)
def test_mapped_windows_cover_any_nominal_month_exactly_once(
    source_fy: int, nominal: date, closed: tuple[bool, bool, bool]
) -> None:
    """Property: for any source fiscal year, any mix of closed and open
    windows, and any nominal month, every versioned rule in the overlaid
    closure has exactly one version in force at that month, and the mapped
    rules keep their formulas and values."""
    start, end = fiscal_year_window(source_fy)
    windows = {
        module: (start.isoformat(), end.isoformat() if is_closed else None)
        for module, is_closed in zip(_COLA_MODULES, closed, strict=True)
    }
    chain_start = fiscal_year_window(fiscal_year_containing(nominal))[0]
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch) / "rulespec-us"
        _window_tree(root, windows=windows, chain_start=chain_start.isoformat())
        build = build_overlay(
            _window_spec(source_fy), root, Path(scratch) / "dest", nominal_month=nominal
        )
        assert rules_without_one_version_at(build.overlay_root, WINDOW_PROGRAM, nominal) == []
        for module in _COLA_MODULES:
            relative = _cola_file(module)
            assert _without_windows(_rules(build.overlay_root / relative)) == (
                _without_windows(_rules(root / relative))
            )


@pytest.mark.parametrize(
    ("module", "window", "message"),
    [
        # FY 2025's window, not FY 2024's.
        ("deductions", ("2024-10-01", None), "2024-10-01..open"),
        # Ends early.
        ("income-eligibility-standards", ("2023-10-01", "2024-03-31"), "2023-10-01..2024-03-31"),
        # Already on the target window (someone re-dated it upstream).
        ("maximum-allotments", ("2025-10-01", "2026-09-30"), "2025-10-01..2026-09-30"),
    ],
)
def test_build_overlay_raises_drift_naming_the_file_when_a_window_moved(
    tmp_path: Path, module: str, window: tuple[str, str | None], message: str
) -> None:
    root = tmp_path / "rulespec-us"
    _window_tree(root, windows={**_TODAY, module: window})

    with pytest.raises(OverlayDriftError) as excinfo:
        build_overlay(_window_spec(), root, tmp_path / "dest", nominal_month=NOMINAL)

    text = str(excinfo.value)
    assert f"{_cola_file(module)}#{module}_additional_member" in text
    assert message in text
    assert "2023-10-01..2024-09-30" in text
    assert "stale" in text


def test_build_overlay_raises_drift_on_extra_versions_or_unversioned_windows(
    tmp_path: Path,
) -> None:
    root = tmp_path / "rulespec-us"
    _window_tree(root, windows=_TODAY)
    relative = _cola_file("deductions")
    rules = _rules(root / relative)
    rules[0]["versions"].append({"effective_from": "2024-10-01", "formula": "430"})
    _write(root / relative, yaml.safe_dump({"rules": rules}, sort_keys=False))
    with pytest.raises(OverlayDriftError, match=f"{relative}#deductions_additional_member has 2 versions"):
        build_overlay(_window_spec(), root, tmp_path / "dest", nominal_month=NOMINAL)

    _window_tree(root, windows=_TODAY)
    rules = _rules(root / relative)
    rules.append({"name": "flat", "kind": "parameter", "effective_from": "2023-10-01", "formula": "1"})
    _write(root / relative, yaml.safe_dump({"rules": rules}, sort_keys=False))
    with pytest.raises(OverlayDriftError, match=f"{relative}#flat carries effective_from, formula"):
        build_overlay(_window_spec(), root, tmp_path / "dest2", nominal_month=NOMINAL)


def test_build_overlay_maps_the_from_to_aliases(tmp_path: Path) -> None:
    root = tmp_path / "rulespec-us"
    _window_tree(root, windows=_TODAY)
    relative = _cola_file("income-eligibility-standards")
    text = (root / relative).read_text().replace("effective_from:", "from:").replace(
        "effective_to:", "to:"
    )
    _write(root / relative, text)

    build = build_overlay(_window_spec(), root, tmp_path / "dest", nominal_month=NOMINAL)

    version = _rules(build.overlay_root / relative)[0]["versions"][0]
    assert (version["from"], version["to"]) == ("2025-10-01", "2026-09-30")
    assert rules_without_one_version_at(build.overlay_root, WINDOW_PROGRAM, NOMINAL) == []


def test_without_the_window_mapping_the_closed_window_selects_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutation check: drop the mapping and today's weekly failure returns.

    The engine reported it as "has no formula version at 2026-01-01" on the
    income-eligibility rules; the overlay's closure check now names the same
    rules at build time.
    """
    root = tmp_path / "rulespec-us"
    _window_tree(root, windows=_TODAY)

    def no_mapping(spec, overlay_root, mapping, nominal_month):
        return {"files": {}}

    monkeypatch.setattr(rulespec_overlay, "_apply_version_windows", no_mapping)
    with pytest.raises(OverlayDriftError) as excinfo:
        build_overlay(_window_spec(), root, tmp_path / "dest", nominal_month=NOMINAL)

    text = str(excinfo.value)
    income = _cola_file("income-eligibility-standards")
    assert "3 versioned rule(s)" in text
    for name in (
        "income-eligibility-standards_additional_member",
        "income-eligibility-standards_table",
        "income-eligibility-standards_amount",
    ):
        assert f"{income}#{name} has 0" in text
    # The open-ended modules still resolve, as they did before 2026-10-01.
    assert _cola_file("deductions") not in text
    assert "2026-01-01" in text


def test_build_overlay_without_nominal_month_is_refused_when_spec_maps_windows(
    tmp_path: Path,
) -> None:
    root = tmp_path / "rulespec-us"
    _window_tree(root, windows=_TODAY)
    with pytest.raises(ValueError, match="pass nominal_month"):
        build_overlay(_window_spec(), root, tmp_path / "dest")


def test_rules_without_one_version_at_flags_gaps_and_overlaps(tmp_path: Path) -> None:
    root = tmp_path / "rulespec-us"
    _write(root / "us/program.yaml", "imports:\n- us:chain\n")
    _write(
        root / "us/chain.yaml",
        yaml.safe_dump(
            {
                "rules": [
                    {"name": "gap", "versions": [{"effective_from": "2026-02-01", "formula": "1"}]},
                    {
                        "name": "overlap",
                        "versions": [
                            {"effective_from": "2025-01-01", "formula": "1"},
                            {"effective_from": "2025-10-01", "formula": "2"},
                        ],
                    },
                    {"name": "ok", "versions": [{"effective_from": "2025-10-01", "effective_to": "2026-01-01", "formula": "1"}]},
                    {"name": "no_versions", "kind": "source_relation"},
                ]
            }
        ),
    )
    assert rules_without_one_version_at(root, "us/program.yaml", NOMINAL) == [
        ("us/chain.yaml", "gap", 0),
        ("us/chain.yaml", "overlap", 2),
    ]


@pytest.mark.parametrize(
    "name",
    [
        "us-az-snap-fy2024",
        "us-ca-snap-fy2024",
        "us-co-snap-fy2024",
        "us-ga-snap-fy2024",
        "us-md-snap-fy2024",
        "us-ny-snap-fy2024",
        "us-tx-snap-fy2024",
    ],
)
def test_packaged_snap_overlays_map_every_fy2024_cola_module(name: str) -> None:
    spec = load_overlay_spec(name)
    assert spec.version_windows == VersionWindowMapping(source_fiscal_year=2024)
    assert rulespec_overlay._window_mapping_files(spec) == [
        _cola_file(module) for module in _COLA_MODULES
    ]


_RULESPEC_US = Path(os.environ.get("RULESPEC_US_SNAP_FY2024_ROOT", ""))


@pytest.mark.skipif(
    _RULESPEC_US == Path()
    or not (_RULESPEC_US / "us/policies/usda/snap/fy-2024-cola").is_dir(),
    reason="set RULESPEC_US_SNAP_FY2024_ROOT to a rulespec-us checkout",
)
@pytest.mark.parametrize(
    "name",
    [
        "us-az-snap-fy2024",
        "us-ca-snap-fy2024",
        "us-co-snap-fy2024",
        "us-ga-snap-fy2024",
        "us-md-snap-fy2024",
        "us-ny-snap-fy2024",
    ],
)
def test_live_overlay_closure_resolves_once_at_the_nominal_month(
    tmp_path: Path, name: str
) -> None:
    """Against a real rulespec-us checkout, every versioned rule in each
    overlaid program's closure has exactly one version at the nominal month,
    and the fy-2024-cola rules keep their encoded formulas and values."""
    from axiom_oracles.bridges.snap_qc_compare import nominal_month

    spec = load_overlay_spec(name)
    if not (_RULESPEC_US / spec.program).is_file():
        pytest.skip(f"{spec.program} is not on this rulespec-us checkout")
    build = build_overlay(
        spec, _RULESPEC_US, tmp_path / "dest", nominal_month=nominal_month()
    )
    assert rules_without_one_version_at(
        build.overlay_root, spec.program, nominal_month()
    ) == []
    for module in _COLA_MODULES:
        relative = _cola_file(module)
        assert _without_windows(_rules(build.overlay_root / relative)) == (
            _without_windows(_rules(_RULESPEC_US / relative))
        )
