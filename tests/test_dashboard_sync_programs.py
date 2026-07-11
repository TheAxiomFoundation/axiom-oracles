from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "dashboard/scripts/sync_programs.py"
SPEC = importlib.util.spec_from_file_location("dashboard_sync_programs", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
sync_programs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync_programs)


def _write_rule(root: Path, suffix: str = ".yaml") -> Path:
    path = root / "us-co" / "policies" / f"snap{suffix}"
    path.parent.mkdir(parents=True)
    path.write_text("rules:\n  - name: snap_allotment\n")
    return path


def test_build_rule_index_uses_country_checkout_and_nested_jurisdiction(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "rulespec-us"
    _write_rule(checkout)

    assert sync_programs.build_rule_index([checkout]) == {
        "snap_allotment": [
            {
                "corpus": "rulespec-us",
                "file": "us-co/policies/snap.yaml",
                "label": "Colorado",
                "scope": "state",
                "country": "US",
                "state": "CO",
            }
        ]
    }


def test_build_rule_index_rejects_flat_jurisdiction_checkout(tmp_path: Path) -> None:
    legacy = tmp_path / "rulespec-us-co"
    (legacy / "policies").mkdir(parents=True)

    with pytest.raises(ValueError, match="exact rulespec-<country>"):
        sync_programs.build_rule_index([legacy])


def test_build_rule_index_rejects_yml_modules(tmp_path: Path) -> None:
    checkout = tmp_path / "rulespec-us"
    _write_rule(checkout, ".yml")

    with pytest.raises(ValueError, match=r"legacy \.yml"):
        sync_programs.build_rule_index([checkout])


def test_build_rule_index_rejects_duplicate_jurisdiction_root(tmp_path: Path) -> None:
    checkout = tmp_path / "rulespec-us"
    _write_rule(checkout)

    with pytest.raises(ValueError, match="duplicate RuleSpec jurisdiction"):
        sync_programs.build_rule_index([checkout, checkout / "us-co"])
