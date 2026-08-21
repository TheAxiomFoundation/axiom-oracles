"""Contract and mutant tests for the all-pending DE closure ledgers.

The DE discovery producer deliberately does not disposition law.  Facts come
from pinned corpus, RuleSpec, certificate, and discovery-snapshot bytes;
absence of a committed decision derives a pending row.  These tests keep the
two axes separate: a leaf may already be known to be ``law_derived`` while its
workflow status remains ``pending``.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).parents[1]
SCRIPT = REPO_ROOT / "scripts" / "de_closure_ledger.py"
REFRESH_SCRIPT = REPO_ROOT / "scripts" / "refresh_de_instrument_graph.py"
SNAPSHOT = REPO_ROOT / "conformance" / "closure" / "de-instrument-graph.json"
PROGRAMS = (
    "de/kindergeld",
    "de/unterhaltsvorschuss",
    "de/rv-employee-contribution",
)
KINDERGELD_LAW_DERIVED = {
    "claimant_entitlement",
    "qualifying_child_count",
    "recipient_priority",
    "substitute_child_benefit_exclusion",
}
EXPECTED_SPINE_COUNTS = {
    "de/kindergeld": 18,
    "de/unterhaltsvorschuss": 12,
    "de/rv-employee-contribution": 3,
}
EXPECTED_LEAVES = {
    "de/kindergeld": {
        "child_allowances_under_sections_31_and_32_6_1_are_increased",
        "claimant_entitlement",
        "correspondingly_increased_kindergeld_amount",
        "month_is_on_or_after_first_qualifying_month",
        "month_is_on_or_before_last_qualifying_month",
        "qualifying_child_count",
        "recipient_priority",
        "substitute_child_benefit_exclusion",
    },
    "de/unterhaltsvorschuss": {
        "child_allowances_under_sections_31_and_32_6_1_are_increased",
        "child_is_in_first_age_stage_under_section_1612a",
        "child_is_in_second_age_stage_under_section_1612a",
        "child_is_in_third_age_stage_under_section_1612a",
        "correspondingly_increased_kindergeld_amount",
        "first_child_kindergeld",
        "minimum_maintenance_for_age_stage",
        "month_is_on_or_after_first_qualifying_month",
        "month_is_on_or_before_last_qualifying_month",
    },
    "de/rv-employee-contribution": {"total_pension_insurance_contribution"},
}
EXPECTED_MEASURED = {
    "de/kindergeld": (18, 28, 4, 1, 0, 0),
    "de/unterhaltsvorschuss": (12, 20, 0, 2, 2, 1),
    "de/rv-employee-contribution": (3, 11, 0, 1, 2, 1),
}


def _load_script():
    spec = importlib.util.spec_from_file_location("de_closure_ledger_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_refresh_script():
    spec = importlib.util.spec_from_file_location(
        "refresh_de_instrument_graph_test", REFRESH_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _artifact_items(module) -> list[tuple[str, Path]]:
    paths = module.ARTIFACT_PATHS
    assert isinstance(paths, dict)
    assert set(paths) == set(PROGRAMS)
    return [(program, Path(paths[program])) for program in PROGRAMS]


def _document(module, path: Path) -> dict:
    document = module.load_document(path)
    assert isinstance(document, dict)
    return document


def _write_document(path: Path, document: dict) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))


def _assert_strict_count(value: object) -> None:
    assert isinstance(value, int)
    assert not isinstance(value, bool)
    assert value >= 0


def test_public_api_and_three_artifact_paths() -> None:
    module = _load_script()
    assert callable(module.load_document)
    assert callable(module.validate_artifact)
    assert callable(module.verify_artifact)
    assert callable(module.main)
    for _, path in _artifact_items(module):
        assert path.is_file(), path


def test_committed_snapshot_receipts_and_pending_frontiers_are_valid() -> None:
    refresh = _load_refresh_script()
    snapshot = json.loads(SNAPSHOT.read_bytes())
    refresh.validate_snapshot(snapshot)
    assert snapshot["channels"]["corpus_release"]["scanned_row_count"] == 3548
    assert snapshot["channels"]["subject_matter_search"]["state"] == "unretrieved"
    assert all(
        row["state"] == "unretrieved"
        for row in snapshot["channels"]["subject_matter_search"]["attempts"]
    )
    assert snapshot["channels"]["citation_scan"]["state"] == "not_yet_available"
    assert snapshot["channels"]["citation_scan"]["issue"] == "axiom-corpus#611"
    assert all(
        instrument["status"] == "pending"
        for program in snapshot["programs"]
        for instrument in program["instruments"]
    )
    kindergeld = next(
        row for row in snapshot["programs"] if row["id"] == "de/kindergeld"
    )
    assert [row["id"] for row in kindergeld["seed_bindings"]] == [
        f"de-kg-instr-{number:03d}" for number in range(1, 6)
    ]
    assert all(row["status"] == "pending" for row in kindergeld["seed_bindings"])


@pytest.mark.parametrize(
    "mutation",
    (
        "channel_receipt",
        "unknown_discovery_ref",
        "duplicate_id",
        "nonpending",
        "source_binding",
        "duplicate_evidence",
        "subject_state",
    ),
)
def test_snapshot_mutants_are_rejected(mutation: str) -> None:
    refresh = _load_refresh_script()
    snapshot = json.loads(SNAPSHOT.read_bytes())
    if mutation == "channel_receipt":
        snapshot["channels"]["citation_scan"]["reason"] += " forged"
    elif mutation == "unknown_discovery_ref":
        snapshot["programs"][0]["instruments"][0]["discovery_refs"] = [
            "not-a-captured-row"
        ]
        snapshot = refresh._add_receipt(snapshot)
    elif mutation == "duplicate_id":
        instruments = snapshot["programs"][0]["instruments"]
        instruments[1]["id"] = instruments[0]["id"]
        instruments.sort(key=lambda row: row["id"])
        snapshot = refresh._add_receipt(snapshot)
    elif mutation == "nonpending":
        snapshot["programs"][0]["instruments"][0]["status"] = "encoded"
        snapshot = refresh._add_receipt(snapshot)
    elif mutation == "source_binding":
        snapshot["source"]["sha256"] = "0" * 64
        snapshot = refresh._add_receipt(snapshot)
    elif mutation == "duplicate_evidence":
        channel = snapshot["channels"]["corpus_release"]
        channel["evidence"].append(copy.deepcopy(channel["evidence"][0]))
        snapshot["channels"]["corpus_release"] = refresh._add_receipt(channel)
        snapshot = refresh._add_receipt(snapshot)
    else:
        channel = snapshot["channels"]["subject_matter_search"]
        channel["state"] = "retrieved"
        snapshot["channels"]["subject_matter_search"] = refresh._add_receipt(channel)
        snapshot = refresh._add_receipt(snapshot)

    with pytest.raises(refresh.CaptureError):
        refresh.validate_snapshot(snapshot)


@pytest.mark.parametrize("program", PROGRAMS)
def test_committed_ledgers_are_valid_and_exactly_open(program: str) -> None:
    module = _load_script()
    path = Path(module.ARTIFACT_PATHS[program])
    document = _document(module, path)
    summary = module.validate_artifact(document)

    assert document["schema"] == "axiom_oracles.closure.ledger.v3"
    assert document["program"]["id"] == program
    assert isinstance(document["computed"]["closed"], bool)
    assert document["computed"]["closed"] is False
    assert summary.closed is False


@pytest.mark.parametrize("program", PROGRAMS)
def test_all_pending_counts_and_lists_agree(program: str) -> None:
    module = _load_script()
    document = _document(module, Path(module.ARTIFACT_PATHS[program]))
    computed = document["computed"]

    ledger = computed["ledger"]
    provision_counts = computed["provision_counts"]
    provision_pending = computed["pending"]
    for value in provision_counts.values():
        _assert_strict_count(value)
    assert provision_counts["total"] == len(ledger)
    assert len(ledger) == EXPECTED_SPINE_COUNTS[program]
    assert provision_counts["pending"] == len(provision_pending) == len(ledger)
    assert provision_counts["encoded"] == 0
    assert provision_counts["partially-encoded"] == 0
    assert provision_counts["classified-with-reason"] == 0
    assert provision_counts["excluded-with-reason"] == 0
    assert computed["partially_encoded"] == []
    assert all(row["status"] == "pending" for row in ledger)
    assert provision_pending == [row["citation_path"] for row in ledger]

    frontier = computed["instrument_frontier"]
    instrument_ledger = frontier["ledger"]
    instrument_counts = frontier["counts"]
    for value in instrument_counts.values():
        _assert_strict_count(value)
    assert instrument_counts["total"] == len(instrument_ledger)
    assert instrument_counts["pending"] == len(frontier["pending"])
    assert instrument_counts["pending"] == len(instrument_ledger)
    assert instrument_counts["encoded"] == 0
    assert instrument_counts["classified-with-reason"] == 0
    assert instrument_counts["excluded-with-reason"] == 0
    assert all(row["status"] == "pending" for row in instrument_ledger)
    assert frontier["pending"] == [row["id"] for row in instrument_ledger]
    assert frontier["complete"] is False

    decisions = document["committed_decisions"]
    assert decisions == {
        "provisions": [],
        "instrument_dispositions": [],
        "leaf_classifications": [],
    }


@pytest.mark.parametrize("program", PROGRAMS)
def test_leaf_frontier_is_explicit_typed_and_pending(program: str) -> None:
    module = _load_script()
    document = _document(module, Path(module.ARTIFACT_PATHS[program]))
    leaves = document["generated_facts"]["leaf_frontier"]
    assert leaves
    assert all(row["status"] == "pending" for row in leaves)
    assert {row["leaf_kind"] for row in leaves} <= {
        "law_derived",
        "unclassified",
    }
    assert {row["input"] for row in leaves} == EXPECTED_LEAVES[program]

    law_derived = {
        row["input"] for row in leaves if row["leaf_kind"] == "law_derived"
    }
    if program == "de/kindergeld":
        assert law_derived == KINDERGELD_LAW_DERIVED
    else:
        assert law_derived == set()
    assert all(
        row["leaf_kind"] == "unclassified"
        for row in leaves
        if row["input"] not in law_derived
    )

    boundary = document["computed"]["boundary_frontier"]
    assert boundary["input_count"] == len(leaves)
    assert boundary["pending_count"] == len(boundary["pending"]) == len(leaves)
    assert boundary["complete"] is False

    dependency = document["computed"]["dependency_closure"]
    for key in (
        "open_dependency_count",
        "law_derived_input_count",
        "unclassified_input_count",
        "instruments_bearing_on_computed_count",
    ):
        _assert_strict_count(dependency[key])
    assert dependency["law_derived_input_count"] == len(
        dependency["law_derived_inputs"]
    )
    assert dependency["unclassified_input_count"] == len(
        dependency["unclassified_inputs"]
    )
    assert dependency["instruments_bearing_on_computed_count"] == len(
        dependency["instruments_bearing_on_computed"]
    )
    assert dependency["open_dependency_count"] == (
        len(dependency["law_derived_inputs"])
        + len(dependency["unclassified_inputs"])
        + len(dependency["instruments_bearing_on_computed"])
    )
    assert dependency["closed"] is False


@pytest.mark.parametrize("program", PROGRAMS)
def test_measured_denominators_are_scalar_and_rederived(program: str) -> None:
    module = _load_script()
    document = _document(module, Path(module.ARTIFACT_PATHS[program]))
    measured = document["computed"]["measured_denominators"]
    assert set(measured) == {
        "spine_rows",
        "bearing_candidate_instruments",
        "law_derived_leaf_nodes",
        "max_depth_estimate",
        "remaining_oracle_work",
        "remaining_executable_work",
    }
    for value in measured.values():
        _assert_strict_count(value)
    assert measured["spine_rows"] == len(document["computed"]["ledger"])
    assert measured["bearing_candidate_instruments"] == len(
        document["computed"]["instrument_frontier"]["ledger"]
    )
    assert measured["law_derived_leaf_nodes"] == len(
        document["computed"]["dependency_closure"]["law_derived_inputs"]
    )
    assert tuple(measured[key] for key in (
        "spine_rows",
        "bearing_candidate_instruments",
        "law_derived_leaf_nodes",
        "max_depth_estimate",
        "remaining_oracle_work",
        "remaining_executable_work",
    )) == EXPECTED_MEASURED[program]


@pytest.mark.parametrize("mutation", ("candidate_count", "duplicate_leaf_id"))
def test_generated_fact_shape_mutants_are_rejected(mutation: str) -> None:
    module = _load_script()
    document = copy.deepcopy(
        _document(module, Path(module.ARTIFACT_PATHS["de/kindergeld"]))
    )
    generated = document["generated_facts"]
    if mutation == "candidate_count":
        generated["instrument_graph"]["candidate_count"] = 0
    else:
        generated["leaf_frontier"][1]["id"] = generated["leaf_frontier"][0]["id"]
        document["computed"] = module._computed(
            generated["provision_spine"],
            generated["leaf_frontier"],
            generated["instrument_graph"],
            generated["measurement_basis"],
        )

    with pytest.raises(ValueError):
        module.validate_artifact(document)


@pytest.mark.parametrize("program", PROGRAMS)
def test_forged_complete_instrument_frontier_is_rejected(program: str) -> None:
    module = _load_script()
    document = copy.deepcopy(
        _document(module, Path(module.ARTIFACT_PATHS[program]))
    )
    frontier = document["computed"]["instrument_frontier"]
    frontier["pending"] = []
    frontier["counts"]["pending"] = 0
    frontier["complete"] = True
    document["computed"]["closed"] = True

    with pytest.raises(ValueError):
        module.validate_artifact(document)


@pytest.mark.parametrize(
    "count_path",
    (
        ("provision_counts", "pending"),
        ("instrument_frontier", "counts", "pending"),
        ("dependency_closure", "open_dependency_count"),
        ("measured_denominators", "spine_rows"),
        ("measured_denominators", "law_derived_leaf_nodes"),
        ("measured_denominators", "remaining_oracle_work"),
        ("measured_denominators", "remaining_executable_work"),
    ),
)
def test_boolean_is_never_accepted_as_an_integer_count(
    count_path: tuple[str, ...],
) -> None:
    module = _load_script()
    document = copy.deepcopy(
        _document(module, Path(module.ARTIFACT_PATHS["de/kindergeld"]))
    )
    target = document["computed"]
    for key in count_path[:-1]:
        target = target[key]
    target[count_path[-1]] = False

    with pytest.raises(ValueError):
        module.validate_artifact(document)


def test_bare_closed_true_dependency_block_is_rejected() -> None:
    module = _load_script()
    document = copy.deepcopy(
        _document(module, Path(module.ARTIFACT_PATHS["de/kindergeld"]))
    )
    document["computed"]["dependency_closure"] = {"closed": True}
    document["computed"]["closed"] = True

    with pytest.raises(ValueError):
        module.validate_artifact(document)


def test_hand_flipped_top_level_closed_true_is_rejected() -> None:
    module = _load_script()
    document = copy.deepcopy(
        _document(module, Path(module.ARTIFACT_PATHS["de/kindergeld"]))
    )
    document["computed"]["closed"] = True

    with pytest.raises(ValueError):
        module.validate_artifact(document)


@pytest.mark.parametrize(
    "generated_mutation",
    ("corpus_spine", "snapshot_receipt"),
)
def test_full_verifier_rejects_coordinated_generated_fact_mutation(
    tmp_path: Path,
    generated_mutation: str,
) -> None:
    """Purely well-shaped generated facts still have to reproduce from sources."""

    module = _load_script()
    original_path = Path(module.ARTIFACT_PATHS["de/kindergeld"])
    document = copy.deepcopy(_document(module, original_path))
    if generated_mutation == "corpus_spine":
        document["generated_facts"]["provision_spine"][0]["body_sha256"] = (
            "0" * 64
        )
    else:
        document["generated_facts"]["instrument_graph"]["snapshot_sha256"] = (
            "0" * 64
        )
    generated = document["generated_facts"]
    document["computed"] = module._computed(
        generated["provision_spine"],
        generated["leaf_frontier"],
        generated["instrument_graph"],
        generated["measurement_basis"],
    )
    mutant = tmp_path / f"{generated_mutation}.yaml"
    _write_document(mutant, document)
    module.ARTIFACT_PATHS["de/kindergeld"] = mutant

    result = module.verify_artifact(artifact_path=mutant)
    assert result.valid is False
    assert result.errors == ("committed artifact differs from hermetic rederivation",)


@pytest.mark.parametrize("program", PROGRAMS)
def test_full_verifier_accepts_each_committed_artifact(program: str) -> None:
    module = _load_script()
    result = module.verify_artifact(
        artifact_path=Path(module.ARTIFACT_PATHS[program])
    )
    assert result.valid is True, result.errors


def test_check_is_hermetic_for_all_and_each_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()

    def no_network(*_args, **_kwargs):
        raise AssertionError("DE ledger --check attempted network access")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "socket", no_network)

    original_run = subprocess.run

    def local_git_only(argv, *args, **kwargs):
        assert argv[0] == "git"
        assert argv[1] == "-C"
        assert argv[3] in {"rev-parse", "show"}
        assert kwargs["env"]["GIT_NO_LAZY_FETCH"] == "1"
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert not any(str(value).startswith(("http://", "https://")) for value in argv)
        return original_run(argv, *args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", local_git_only)

    assert module.main(["--check", "--artifact", "all"]) == 0
    for _, path in _artifact_items(module):
        assert module.main(["--check", "--artifact", str(path)]) == 0
