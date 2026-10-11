"""Repeated role construction reuses an analysis without changing its result."""

from copy import deepcopy
import json
import subprocess
from unittest.mock import patch

from hypothesis import given, settings, strategies as st
import pytest

from axiom_oracles.adapters.axiom import generic_inputs, runner
from axiom_oracles.bridges import relation_binding
from axiom_oracles.core.case import Case, Entity


def _artifact(owner_slot=1, owner="Household", member="Person", typed=False):
    slots = [member, owner] if owner_slot else [owner, member]
    return {"program": {
        "relations": [{"name": "members", "arity": 2,
                       **({"slot_entities": slots} if typed else {})}],
        "derived": [{"name": "count", "entity": owner, "expr": {
            "kind": "count_related", "relation": "members",
            "current_slot": owner_slot, "related_slot": 1 - owner_slot,
        }}],
    }}


def _tuple(artifact, **kwargs):
    return relation_binding.relation_tuple(
        artifact, "members", owner_id="house", owner_kind="Household",
        related_id="person", related_kind="Person", **kwargs,
    )


def test_role_construction_analyzes_artifact_once_per_batch(monkeypatch):
    artifact = _artifact()
    walks = []
    read_usages = relation_binding._ArtifactRelations._read_usages

    def counted(self, program):
        walks.append(program)
        return read_usages(self, program)

    monkeypatch.setattr(relation_binding._ArtifactRelations, "_read_usages", counted)
    for index in range(120):
        assert relation_binding.relation_tuple(
            artifact, "members", owner_id="house", owner_kind="Household",
            related_id=f"person-{index}", related_kind="Person",
        ) == [f"person-{index}", "house"]
    # One analysis retains its two dependency passes; repeated rows add none.
    assert len(walks) == 2


@pytest.mark.parametrize("size", [40, 120])
def test_producer_and_engine_batch_analysis_count_does_not_grow_with_cases(
    monkeypatch, tmp_path, size,
):
    artifact = _artifact()
    path = tmp_path / "members.compiled.json"
    path.write_text(json.dumps(artifact))
    walks = []
    original = relation_binding._ArtifactRelations._read_usages

    def counted(self, program):
        walks.append(program)
        return original(self, program)

    monkeypatch.setattr(relation_binding._ArtifactRelations, "_read_usages", counted)
    cases = [Case(str(index), "2026-01", entities=tuple(
        Entity(str(person), "Person") for person in range(3)
    )) for index in range(size)]
    projected = generic_inputs.attach_generic_inputs(
        cases, compiled_program_path=path, member_relation="members",
        load_default_mapping=False,
    )
    # Producer owner discovery and construction each analyze one variant.
    assert len(walks) == 4

    def fake_run(command, **kwargs):
        request = json.loads(kwargs["input"])
        assert len(request["dataset"]["relations"]) == 3 * size
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({
            "results": [{"outputs": {}} for _ in cases],
        }), stderr="")

    adapter = runner.AxiomRulesRunner(binary_path=tmp_path / "engine", subprocess_run=fake_run)
    assert len(adapter._run_case_batch_once(projected, ["count"], path)) == size
    # The separately loaded runtime artifact needs one constructor analysis.
    assert len(walks) == 6


def test_constructor_cache_observes_in_place_artifact_mutation():
    artifact = _artifact()
    assert _tuple(artifact) == ["person", "house"]
    expression = artifact["program"]["derived"][0]["expr"]
    expression.update(current_slot=0, related_slot=1)
    assert _tuple(artifact) == ["house", "person"]


def test_constructor_aliases_reuse_the_same_analysis(monkeypatch):
    artifact = _artifact()
    schema = artifact["program"]["relations"][0]
    schema["name"] = "example:module#relation.members"
    calls = []
    original = relation_binding._ArtifactRelations._read_usages

    def counted(self, program):
        calls.append(program)
        return original(self, program)

    monkeypatch.setattr(relation_binding._ArtifactRelations, "_read_usages", counted)
    assert _tuple(artifact) == ["person", "house"]
    assert relation_binding.relation_tuple(
        artifact, schema["name"], owner_id="house", owner_kind="Household",
        related_id="person", related_kind="Person",
    ) == ["person", "house"]
    assert len(calls) == 2


def test_constructor_cache_retains_bounded_artifacts_and_hints(monkeypatch):
    monkeypatch.setattr(relation_binding, "_MAX_CACHED_ARTIFACTS", 2)
    monkeypatch.setattr(relation_binding, "_MAX_CACHED_CONSTRUCTOR_HINTS", 2)
    for _ in range(3):
        artifact = _artifact()
        for kind in ("Person", "Payment", "TaxUnit"):
            relation_binding.relation_tuple(
                artifact, "members", owner_id="house", owner_kind="Household",
                related_id="member", related_kind=kind,
            )
    cache = relation_binding._ARTIFACT_RELATION_CACHE
    assert len(cache) == 2
    assert all(len(entry.analyses) == 2 for entry in cache.values())


@settings(deadline=None)
@given(
    owner=st.sampled_from(["Household", "TaxUnit", "Person", "Org"]),
    member=st.sampled_from(["Person", "Payment", "TaxUnit", "Org"]),
    owner_slot=st.integers(0, 1),
    legacy_owner_slot=st.integers(0, 1),
    typed=st.booleans(),
    inverse=st.booleans(),
)
def test_cached_constructor_matches_fresh_analysis(
    owner, member, owner_slot, legacy_owner_slot, typed, inverse,
):
    artifact = _artifact(owner_slot, owner, member, typed)
    if inverse:
        artifact["program"]["derived"].append({
            "name": "inverse-count", "entity": member, "expr": {
                "kind": "count_related", "relation": "members",
                "current_slot": 1 - owner_slot, "related_slot": owner_slot,
            },
        })
    before = deepcopy(artifact)
    arguments = {
        "owner_id": "owner", "owner_kind": owner,
        "related_id": "member", "related_kind": member,
        "legacy_owner_slot": legacy_owner_slot,
    }

    def outcome(function):
        try:
            return function()
        except relation_binding.RelationBindingError as error:
            return type(error), str(error)

    # Cached and fresh analysis must agree, including conservative errors.
    operations = [
        lambda: relation_binding.relation_tuple(artifact, "members", **arguments),
        lambda: relation_binding.relation_owner_kind(
            artifact, "members", default_owner_kind=owner, related_kind=member,
        ),
    ]
    for operation in operations:
        expected = outcome(operation)
        assert outcome(operation) == expected
        assert outcome(operation) == expected
        with patch.object(
            relation_binding, "_artifact_relation_analysis",
            side_effect=relation_binding._ArtifactRelations,
        ):
            assert outcome(operation) == expected
    assert artifact == before
