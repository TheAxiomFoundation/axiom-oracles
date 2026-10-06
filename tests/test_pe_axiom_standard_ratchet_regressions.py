"""Recorded Axiom status cannot fall when the PolicyEngine issue improves."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison.pe_axiom_standard import (
    RATCHET_RELATIVE_PATH,
    Ratchet,
    Record,
    check_history,
    check_records,
    derive_ratchet,
    effective_ratchet,
    serialize_ratchet,
)

CONCEPT = "us:policies/example#amount"
PE_ISSUE = "https://github.com/PolicyEngine/policyengine-us/issues/123"
DEBT_ISSUE = "https://github.com/TheAxiomFoundation/rulespec-us/issues/123"
COMPANION = {
    "legal_ids": [CONCEPT],
    "tests": [f"rulespec-us@{'a' * 40}:us/policies/example.test.yaml#case"],
}
_SPEC = importlib.util.spec_from_file_location(
    "pe_axiom_standard_ratchet_script",
    Path(__file__).resolve().parents[1] / "scripts" / "pe_axiom_standard.py",
)
assert _SPEC and _SPEC.loader
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)


def _record(record_id: str, *, issue: bool = False, side: str = "missing") -> Record:
    entry = {}
    if side == "companion":
        entry["axiom_companion"] = COMPANION
    elif side == "debt":
        entry["axiom_encoding_debt"] = DEBT_ISSUE
    return Record(
        source="dispositions/example.yaml",
        id=record_id,
        suite="example",
        concept=CONCEPT,
        basis="rows",
        pe_issue=PE_ISSUE if issue else None,
        entry=entry,
    )


def _parse(document: dict) -> Ratchet:
    return Ratchet.from_document(yaml.safe_load(serialize_ratchet(document)))


def _sequence():
    start = [_record("A"), _record("B", issue=True)]
    base = _parse(derive_ratchet(start, None))
    backed = [_record("A", side="companion"), _record("B", issue=True)]
    assert check_records(backed, base) == []
    paid = _parse(derive_ratchet(backed, base))
    assert paid.open_max == 1
    assert paid.grandfathered[backed[0].key]["axiom"] == "companion"
    final = [
        _record("A", issue=True, side="debt"),
        _record("B", issue=True, side="companion"),
    ]
    return start, base, backed, paid, final


def test_issue_improvement_cannot_hide_companion_to_debt_regression() -> None:
    _, base, _, paid, final = _sequence()
    # B pays down the new open item, leaving the aggregate ceiling unchanged.
    assert sum(record.open for record in final) == paid.open_max
    assert check_history(paid, [("base", base), ("paid", paid)]) == []
    errors = check_records(final, paid)
    assert len(errors) == 1
    assert "[A]: grandfathered entry regressed" in errors[0]
    assert "axiom=companion" in errors[0] and "axiom=debt" in errors[0]


@pytest.mark.parametrize("mode", [("--check",), (), ("--raise-ceiling", "debt")])
def test_cli_rejects_issue_improvement_with_companion_downgrade(
    tmp_path: Path, monkeypatch, capsys, mode: tuple[str, ...]
) -> None:
    start, base, backed, paid, final = _sequence()
    live = start
    monkeypatch.setattr(script, "collect_records", lambda root: (live, []))
    monkeypatch.setattr(script, "committed_versions", lambda root: ([], []))
    assert script.main(["--init"], repo_root=tmp_path) == 0
    live = backed
    assert script.main([], repo_root=tmp_path) == 0
    path = tmp_path / RATCHET_RELATIVE_PATH
    pinned = path.read_bytes()
    assert _parse(yaml.safe_load(pinned)) == paid
    monkeypatch.setattr(
        script,
        "committed_versions",
        lambda root: ([("base", base), ("paid", paid)], []),
    )
    live = final
    capsys.readouterr()
    assert script.main(list(mode), repo_root=tmp_path) == 1
    assert "[A]: grandfathered entry regressed" in capsys.readouterr().err
    assert path.read_bytes() == pinned


@pytest.mark.parametrize("mode", [(), ("--raise-ceiling", "debt")])
def test_repin_uses_historical_companion_status_before_dropping_compliant_row(
    tmp_path: Path, monkeypatch, capsys, mode: tuple[str, ...]
) -> None:
    _, base, _, paid, final = _sequence()
    # A reverted working file still carries the pre-companion row; the
    # effective baseline must retain the stronger committed companion status.
    path = tmp_path / RATCHET_RELATIVE_PATH
    path.parent.mkdir()
    path.write_text(serialize_ratchet(derive_ratchet([_record("A"), _record("B", issue=True)], None)))
    pinned = path.read_bytes()
    monkeypatch.setattr(script, "collect_records", lambda root: (final, []))
    monkeypatch.setattr(
        script,
        "committed_versions",
        lambda root: ([("base", base), ("paid", paid)], []),
    )
    assert script.main(list(mode), repo_root=tmp_path) == 1
    assert "axiom=companion" in capsys.readouterr().err
    assert path.read_bytes() == pinned


@settings(max_examples=300, deadline=None, derandomize=True)
@given(
    record_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8),
    other_sides=st.lists(st.sampled_from(("missing", "debt")), min_size=1, max_size=8),
    reverted=st.booleans(),
    reverse=st.booleans(),
)
def test_every_recorded_companion_survives_issue_improvement_and_parallel_paydown(
    record_id: str, other_sides: list[str], reverted: bool, reverse: bool
) -> None:
    """Individual status is monotone even when other records lower open debt."""
    others = [
        _record(f"other-{index}", issue=True, side=side)
        for index, side in enumerate(other_sides)
    ]
    start = [_record(record_id), *others]
    base = _parse(derive_ratchet(start, None))
    backed = [_record(record_id, side="companion"), *others]
    assert check_records(backed, base) == []
    paid = _parse(derive_ratchet(backed, base))
    versions = [("base", base), ("paid", paid)]
    final = [
        _record(record_id, issue=True, side="debt"),
        *[_record(other.id, issue=True, side="companion") for other in others],
    ]
    if reverse:
        final.reverse()
    assert sum(record.open for record in final) <= paid.open_max
    effective = effective_ratchet(base if reverted else paid, versions)
    proposed = derive_ratchet(final, effective)
    errors = check_records(
        final,
        Ratchet(open_max=proposed["open_max"], grandfathered=effective.grandfathered),
    )
    assert len(errors) == 1
    assert f"[{record_id}]: grandfathered entry regressed" in errors[0]


def test_adding_the_issue_while_keeping_the_companion_remains_valid() -> None:
    _, base, _, paid, _ = _sequence()
    improved = [
        _record("A", issue=True, side="companion"),
        _record("B", issue=True, side="companion"),
    ]
    assert check_records(improved, paid) == []
    repinned = _parse(derive_ratchet(improved, paid))
    assert repinned.grandfathered == {}
    assert repinned.open_max == 0
    assert check_history(repinned, [("base", base), ("paid", paid)]) == []
