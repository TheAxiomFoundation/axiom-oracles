"""Focused guard-reversion proofs for NZ program-scoped dependency cones."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
DEPENDENCY_DISPOSITIONS = REPO / "closure" / "nz" / "dependency-dispositions.json"

ACC = "nz/acc-earners-levy"
WEP = "nz/winter-energy-payment"
ACC_INPUT = "engine_request:acc_earnings_for_earners_levy"
UNATTRIBUTED_LAW_INPUT = "host_rule:ORACLE_IWTC_WEEKLY_THRESHOLD"

EXPECTED_CONES = {
    "nz/acc-earners-levy": (1, 2, 3),
    "nz/winter-energy-payment": (2, 1, 3),
    "nz/main-benefits": (11, 1, 12),
    "nz/income-tax": (1, 25, 26),
    "nz/accommodation-supplement": (26, 3, 29),
    "nz/independent-earner-tax-credit": (7, 32, 39),
    "nz/working-for-families": (80, 33, 113),
}
EXPECTED_RANKING = list(EXPECTED_CONES)


def _load_nz_closure():
    name = "nz_closure_program_cone_mutants"
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts/nz_closure.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _rulespec_paths(module) -> set[str]:
    source = module.load_source()
    return {row["path"] for row in source["rulespec"]["files"]}


def _acc_grounding(document: dict) -> dict:
    return next(
        row
        for row in document["input_grounding"]
        if row["source_surface"] == "engine_request"
        and row["name"] == "acc_earnings_for_earners_levy"
    )


def _render(document: dict) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def test_reachable_input_missing_program_is_rejected_and_guard_restores():
    """A syntactically honest programs:[] cannot erase ACC reachability."""

    module = _load_nz_closure()
    dispositions, _raw = module._load_dependency_dispositions()
    source_comparison, _source_raw = module._load_source_comparison_catalog()
    paths = _rulespec_paths(module)
    baseline = module._canonical_dependency_grounding(
        dispositions,
        source_comparison,
        rulespec_paths=paths,
    )

    mutant = copy.deepcopy(dispositions)
    row = _acc_grounding(mutant)
    assert row["programs"] == [ACC]
    row["programs"] = []
    row["attribution_reason"] = (
        "Mutant claims the trace-reachable ACC input belongs to no view."
    )

    with pytest.raises(module.ClosureError, match="programs drifted"):
        module._canonical_dependency_grounding(
            mutant,
            source_comparison,
            rulespec_paths=paths,
        )

    restored = module._canonical_dependency_grounding(
        dispositions,
        source_comparison,
        rulespec_paths=paths,
    )
    assert restored == baseline


def test_coordinated_attribution_shrink_cannot_beat_fresh_build(monkeypatch):
    """Moving ACC's input to another valid view is rejected by a fresh walk."""

    module = _load_nz_closure()
    original = DEPENDENCY_DISPOSITIONS.read_bytes()
    with tempfile.TemporaryDirectory(
        prefix=".nz-program-cone-mutant-", dir=REPO
    ) as raw:
        local_path = Path(raw) / DEPENDENCY_DISPOSITIONS.name
        local_path.write_bytes(original)
        monkeypatch.setattr(module, "DEPENDENCY_DISPOSITIONS_PATH", local_path)

        baseline = module.build(module.load_source())
        assert module.validate_artifact(baseline, repo_root=REPO) == baseline

        mutant = json.loads(original)
        row = _acc_grounding(mutant)
        assert row["programs"] == [ACC]
        row["programs"] = [WEP]
        try:
            local_path.write_text(_render(mutant), encoding="utf-8")
            with pytest.raises(module.ClosureError, match="programs drifted"):
                module.build(module.load_source())
        finally:
            local_path.write_bytes(original)

        assert local_path.read_bytes() == original
        assert module.build(module.load_source()) == baseline
        assert module.validate_artifact(baseline, repo_root=REPO) == baseline


def test_unattributed_law_row_stays_global_and_scoped_exclusion_restores():
    """programs:[] narrows no cone and never lowers jurisdiction debt."""

    module = _load_nz_closure()
    baseline = module.build(module.load_source())
    global_dependency = baseline["computed"]["dependency_closure"]
    grounding = baseline["computed"]["input_grounding"]["ledger"]
    host_row = next(
        row
        for row in grounding
        if f"{row['source_surface']}:{row['name']}" == UNATTRIBUTED_LAW_INPUT
    )

    assert host_row["leaf_kind"] == "law_derived"
    assert host_row["programs"] == []
    assert host_row["attribution_reason"].strip()
    assert global_dependency["open_dependency_count"] == 268
    assert UNATTRIBUTED_LAW_INPUT in global_dependency["law_derived_inputs"]
    for program in baseline["programs"].values():
        scoped = program["dependency_closure"]
        assert scoped["jurisdiction_open_dependency_count"] == 268
        assert UNATTRIBUTED_LAW_INPUT not in scoped["law_derived_inputs"]

    mutant = copy.deepcopy(baseline)
    mutant_global = mutant["computed"]["dependency_closure"]
    mutant_global["law_derived_inputs"].remove(UNATTRIBUTED_LAW_INPUT)
    mutant_global["open_dependency_count"] -= 1
    with pytest.raises(module.ClosureError, match="does not rederive"):
        module.validate_artifact(mutant, repo_root=REPO)

    assert module.validate_artifact(baseline, repo_root=REPO) == baseline


@pytest.mark.parametrize(
    ("mutation", "error"),
    (
        (
            "missing_rule",
            "evaluation_order must be an exact unique 176-rule permutation",
        ),
        ("reverse", "evaluation_order is not topological"),
    ),
)
def test_compiled_evaluation_order_mutants_are_rejected_and_bytes_restore(
    mutation, error, tmp_path, monkeypatch
):
    """Receipt-valid order mutations cannot alter the formula walk."""

    module = _load_nz_closure()
    original = module.COMPILED_PROGRAM_PATH.read_bytes()
    local_path = tmp_path / module.COMPILED_PROGRAM_PATH.name
    local_path.write_bytes(original)
    monkeypatch.setattr(module, "COMPILED_PROGRAM_PATH", local_path)
    monkeypatch.setattr(
        module,
        "COMPILED_PROGRAM_SHA256",
        hashlib.sha256(original).hexdigest(),
    )
    roots = {
        program: sorted(spec["roots"])
        for program, spec in module.PROGRAM_VIEWS.items()
    }
    baseline = module._program_reached_compiled_inputs(roots)

    mutant = json.loads(original)
    order = mutant["metadata"]["evaluation_order"]
    if mutation == "missing_rule":
        order.pop()
    else:
        order.reverse()
    try:
        local_path.write_text(json.dumps(mutant), encoding="utf-8")
        monkeypatch.setattr(
            module,
            "COMPILED_PROGRAM_SHA256",
            hashlib.sha256(local_path.read_bytes()).hexdigest(),
        )
        with pytest.raises(module.ClosureError, match=error):
            module._program_reached_compiled_inputs(roots)
    finally:
        local_path.write_bytes(original)
        monkeypatch.setattr(
            module,
            "COMPILED_PROGRAM_SHA256",
            hashlib.sha256(original).hexdigest(),
        )

    assert local_path.read_bytes() == original
    assert module._program_reached_compiled_inputs(roots) == baseline


def test_exact_program_cone_ranking_and_acc_spine():
    module = _load_nz_closure()
    summary = module.build(module.load_source())

    observed = {}
    for program, document in summary["programs"].items():
        dependency = document["dependency_closure"]
        observed[program] = (
            len(dependency["law_derived_inputs"]),
            len(dependency["instruments_bearing_on_computed"]),
            dependency["open_dependency_count"],
        )
        assert dependency["jurisdiction_open_dependency_count"] == 268
        assert dependency["closed"] is False
    assert observed == EXPECTED_CONES
    assert sorted(observed, key=lambda program: (observed[program][2], program)) == (
        EXPECTED_RANKING
    )

    acc = summary["programs"][ACC]
    assert acc["root_nodes"] == [
        "nz:regulations/acc/earners_levy#acc_standard_earners_levy_including_gst"
    ]
    assert acc["dependency_closure"]["law_derived_inputs"] == [ACC_INPUT]
    assert acc["dependency_closure"]["instruments_bearing_on_computed"] == [
        "https://www.ird.govt.nz/deductions-from-salary-and-wages",
        "https://www.legislation.govt.nz/act/public/1985/141/en/latest/",
    ]
    spine = acc["spine_frontier"]
    assert spine["complete"] is True
    assert spine["pending"] == []
    assert spine["citation_count"] == 2
    assert [row["citation_path"] for row in spine["rows"]] == [
        "nz/regulation/regulation/public/2025/0018/regulation/4",
        "nz/regulation/regulation/public/2025/0018/regulation/5",
    ]
    assert {row["status"] for row in spine["rows"]} == {"encoded"}
