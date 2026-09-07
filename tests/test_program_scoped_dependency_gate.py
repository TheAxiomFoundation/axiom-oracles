"""Focused mutants for the central program-scoped dependency gate."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
PROGRAM = "nz/program-a"
OTHER_PROGRAM = "nz/program-b"


def _load_certify():
    spec = importlib.util.spec_from_file_location(
        "certify_program_scope_mutants", REPO / "scripts" / "certify.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _dependency(law: list[str], bearing: list[str]) -> dict:
    count = len(law) + len(bearing)
    return {
        "open_dependency_count": count,
        "law_derived_inputs": law,
        "instruments_bearing_on_computed": bearing,
        "closed": count == 0,
    }


def _grounding(name: str, *, programs: list[str] | None = None) -> dict:
    row = {
        "source_surface": "engine_request",
        "name": name,
        "leaf_kind": "law_derived",
        "reason": "The legal rule remains to be encoded.",
    }
    if programs is not None:
        row["programs"] = programs
        if not programs:
            row["attribution_reason"] = (
                "No certificate view reaches this synthetic host-only input."
            )
    return row


def _computed(
    *,
    grounding: list[dict],
    bearing_rows: list[dict],
    law: list[str],
    bearing: list[str],
) -> dict:
    return {
        "dependency_closure": _dependency(law, bearing),
        "input_grounding": {"ledger": grounding},
        "instrument_frontier": {"ledger": bearing_rows},
    }


def _complete_spine() -> dict:
    statuses = {"encoded": 1, "classified": 0, "excluded": 0, "pending": 0}
    return {
        "complete": True,
        "scope_adjudication_pending": False,
        "body_hash_ledger_complete": True,
        "blockers": [],
        "requested_legal_subgraph_scope": {
            "total": 1,
            "by_status": statuses,
            "instrument_counts": [{"total": 1, "by_status": statuses}],
        },
    }


def test_unattributed_ledger_preserves_exact_global_four_field_path():
    """MUTANT: a scoped producer summary cannot opt a legacy ledger into P3."""

    certify = _load_certify()
    law = ["engine_request:a"]
    bearing = ["https://example.test/instrument"]
    computed = _computed(
        grounding=[_grounding("a")],
        bearing_rows=[{"eli": bearing[0]}],
        law=law,
        bearing=bearing,
    )
    forged_scoped = {"dependency_closure": _dependency([], [])}

    summary, passes, attributed = certify._central_dependency_closure(
        PROGRAM, computed, forged_scoped
    )

    assert attributed is False
    assert passes is False
    assert summary == computed["dependency_closure"]
    assert set(summary) == {
        "open_dependency_count",
        "law_derived_inputs",
        "instruments_bearing_on_computed",
        "closed",
    }


@pytest.mark.parametrize(
    "program",
    ("dk/boerne-og-ungeydelse", "us-co/snap", "us/tariff-duty"),
)
def test_real_legacy_certificates_remain_byte_identical(program):
    """An actual no-attribution producer keeps its committed certificate bytes."""

    certify = _load_certify()
    certificate = certify.build_certificate(program, certify.PROGRAMS[program])
    rendered = (json.dumps(certificate, indent=2, sort_keys=True) + "\n").encode()

    assert rendered == certify._out_path(program).read_bytes()
    dependency = certificate["verdicts"]["closed"].get("dependency_closure")
    if dependency is not None:
        assert "jurisdiction_open_dependency_count" not in dependency


def test_no_program_rows_remain_in_the_jurisdiction_count():
    """An explicit empty attribution narrows no cone but never leaves NZ totals."""

    certify = _load_certify()
    law = ["engine_request:host", "engine_request:owned"]
    bearing = ["https://example.test/no-view-instrument"]
    computed = _computed(
        grounding=[
            _grounding("host", programs=[]),
            _grounding("owned", programs=[PROGRAM]),
        ],
        bearing_rows=[{"eli": bearing[0], "programs": []}],
        law=law,
        bearing=bearing,
    )

    summary, passes, attributed = certify._central_dependency_closure(
        PROGRAM, computed, {}
    )

    assert attributed is True
    assert passes is False
    assert summary == {
        "open_dependency_count": 1,
        "jurisdiction_open_dependency_count": 3,
        "law_derived_inputs": ["engine_request:owned"],
        "instruments_bearing_on_computed": [],
        "closed": False,
    }


def test_program_cone_filters_both_dependency_classes_and_checks_scoped_copy():
    certify = _load_certify()
    law = ["engine_request:a", "engine_request:b", "engine_request:shared"]
    bearing = ["https://example.test/a", "https://example.test/b"]
    computed = _computed(
        grounding=[
            _grounding("a", programs=[PROGRAM]),
            _grounding("b", programs=[OTHER_PROGRAM]),
            _grounding("shared", programs=[PROGRAM, OTHER_PROGRAM]),
        ],
        bearing_rows=[
            {"eli": bearing[0], "programs": [PROGRAM]},
            {"eli": bearing[1], "programs": [OTHER_PROGRAM]},
        ],
        law=law,
        bearing=bearing,
    )
    scoped_copy = _dependency(
        ["engine_request:a", "engine_request:shared"],
        ["https://example.test/a"],
    )
    scoped_copy["jurisdiction_open_dependency_count"] = 5

    summary, passes, attributed = certify._central_dependency_closure(
        PROGRAM, computed, {"dependency_closure": scoped_copy}
    )

    assert attributed is True
    assert passes is False
    assert summary == {
        "open_dependency_count": 3,
        "jurisdiction_open_dependency_count": 5,
        "law_derived_inputs": ["engine_request:a", "engine_request:shared"],
        "instruments_bearing_on_computed": ["https://example.test/a"],
        "closed": False,
    }


@pytest.mark.parametrize(
    "mutation",
    (
        "partial_input_attribution",
        "malformed_input_attribution",
        "missing_bearing_attribution",
        "missing_bearing_row",
        "duplicate_bearing_row",
        "missing_unattributed_reason",
    ),
)
def test_partial_or_malformed_attribution_reds_and_guard_reversion_passes(mutation):
    certify = _load_certify()
    law = ["engine_request:a"]
    bearing = ["https://example.test/a"]
    original = _computed(
        grounding=[
            _grounding("a", programs=[PROGRAM]),
            {
                "source_surface": "engine_request",
                "name": "world-fact",
                "leaf_kind": "world_fact",
                "reason": "An observable event.",
                "programs": [PROGRAM],
            },
            _grounding("host-only", programs=[]),
        ],
        bearing_rows=[{"eli": bearing[0], "programs": [PROGRAM]}],
        law=law,
        bearing=bearing,
    )
    baseline = certify._central_dependency_closure(PROGRAM, original, {})
    assert baseline[0].get("malformed") is not True

    mutant = copy.deepcopy(original)
    if mutation == "partial_input_attribution":
        mutant["input_grounding"]["ledger"][1].pop("programs")
    elif mutation == "malformed_input_attribution":
        mutant["input_grounding"]["ledger"][0]["programs"] = PROGRAM
    elif mutation == "missing_bearing_attribution":
        mutant["instrument_frontier"]["ledger"][0].pop("programs")
    elif mutation == "missing_bearing_row":
        mutant["instrument_frontier"]["ledger"].clear()
    elif mutation == "duplicate_bearing_row":
        mutant["instrument_frontier"]["ledger"].append(
            copy.deepcopy(mutant["instrument_frontier"]["ledger"][0])
        )
    else:
        mutant["input_grounding"]["ledger"][2].pop("attribution_reason")

    summary, passes, attributed = certify._central_dependency_closure(
        PROGRAM, mutant, {}
    )
    assert attributed is True
    assert passes is False
    assert summary["malformed"] is True
    assert summary["jurisdiction_open_dependency_count"] == 2

    assert certify._central_dependency_closure(PROGRAM, original, {}) == baseline


@pytest.mark.parametrize("count_kind", ("global", "scoped", "jurisdiction"))
def test_forged_counts_red_and_guard_reversion_passes(count_kind):
    certify = _load_certify()
    law = ["engine_request:a"]
    computed = _computed(
        grounding=[_grounding("a", programs=[PROGRAM])],
        bearing_rows=[],
        law=law,
        bearing=[],
    )
    scoped = {"dependency_closure": _dependency(law, [])}
    scoped["dependency_closure"]["jurisdiction_open_dependency_count"] = 1
    baseline = certify._central_dependency_closure(PROGRAM, computed, scoped)
    assert baseline[0].get("malformed") is not True

    mutant_computed = copy.deepcopy(computed)
    mutant_scoped = copy.deepcopy(scoped)
    if count_kind == "global":
        mutant_computed["dependency_closure"]["open_dependency_count"] = 0
    elif count_kind == "scoped":
        mutant_scoped["dependency_closure"]["open_dependency_count"] = 0
    else:
        mutant_scoped["dependency_closure"][
            "jurisdiction_open_dependency_count"
        ] = 0

    summary, passes, attributed = certify._central_dependency_closure(
        PROGRAM, mutant_computed, mutant_scoped
    )
    assert attributed is True
    assert passes is False
    assert summary["malformed"] is True

    assert certify._central_dependency_closure(PROGRAM, computed, scoped) == baseline


def test_producer_gate_selects_scoped_frontier_and_spine_in_attributed_mode(
    tmp_path, monkeypatch
):
    """MUTANT: global open blocks cannot replace P's complete scoped blocks."""

    certify = _load_certify()
    law = ["engine_request:host"]
    bearing = ["https://example.test/other-program"]
    global_instrument = {
        "instrument_count": 1,
        "supplemental_count": 0,
        "counts": {"total": 1, "pending": 1},
        "pending": bearing,
        "complete": False,
        "ledger": [{"eli": bearing[0], "programs": [OTHER_PROGRAM]}],
    }
    scoped_dependency = _dependency([], [])
    scoped_dependency["jurisdiction_open_dependency_count"] = 2
    scoped_instrument = {
        "instrument_count": 0,
        "supplemental_count": 0,
        "counts": {"total": 0, "pending": 0},
        "pending": [],
        "complete": True,
        "ledger": [],
    }
    document = {
        "corpus_release": "synthetic",
        "rulespec_commit": "a" * 40,
        "computed": {
            "dependency_closure": _dependency(law, bearing),
            "input_grounding": {
                "ledger": [_grounding("host", programs=[])]
            },
            "instrument_frontier": global_instrument,
            "spine_frontier": {"complete": False},
        },
        "programs": {
            PROGRAM: {
                "closed": True,
                "dependency_closure": scoped_dependency,
                "instrument_frontier": scoped_instrument,
                "spine_frontier": _complete_spine(),
                "pending_citations": [],
            }
        },
    }
    artifact = tmp_path / "closure.json"
    artifact.write_text(json.dumps(document))

    class Producer:
        @staticmethod
        def validate_artifact(value, *, repo_root):
            assert repo_root == certify.REPO_ROOT
            return value

    monkeypatch.setattr(certify, "_repo_artifact_path", lambda *_args, **_kwargs: artifact)
    monkeypatch.setattr(certify, "_producer_module", lambda _name: Producer())
    monkeypatch.setattr(certify, "sha256_of", lambda _path: "0" * 64)

    verdict = certify._producer_closed_verdict(
        PROGRAM,
        {"computed": {"closed": {"artifact": "x", "producer": "y"}}},
        [],
    )

    assert verdict is not None
    assert verdict["value"] is True
    assert verdict["instrument_frontier"]["complete"] is True
    assert verdict["spine_frontier"]["complete"] is True
    assert verdict["dependency_closure"] == {
        "open_dependency_count": 0,
        "jurisdiction_open_dependency_count": 2,
        "law_derived_inputs": [],
        "instruments_bearing_on_computed": [],
        "closed": True,
    }
