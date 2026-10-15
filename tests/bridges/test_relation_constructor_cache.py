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


def _artifact(owner_slot=1, owner="Household", member="Person", typed=True):
    slots = [member, owner] if owner_slot else [owner, member]
    artifact = {
        "program": {
            "relations": [
                {
                    "name": "members",
                    "arity": 2,
                    **({"slot_entities": slots} if typed else {}),
                }
            ],
            "derived": [
                {
                    "name": "count",
                    "entity": owner,
                    "expr": {
                        "kind": "count_related",
                        "relation": "members",
                        "current_slot": owner_slot,
                        "related_slot": 1 - owner_slot,
                    },
                }
            ],
        }
    }
    if owner == member and typed:
        artifact["program"]["relations"].append(
            {
                "name": "wrapper",
                "arity": 2,
                "derivation": {
                    "source_relation": "members",
                    "current_slot": owner_slot,
                    "related_slot": 1 - owner_slot,
                    "predicate": {
                        "kind": "comparison",
                        "op": "eq",
                        "left": {
                            "kind": "literal",
                            "value": {"kind": "integer", "value": 1},
                        },
                        "right": {
                            "kind": "literal",
                            "value": {"kind": "integer", "value": 1},
                        },
                    },
                },
            }
        )
    return artifact


def _tuple(artifact, **kwargs):
    return relation_binding.relation_tuple(
        artifact,
        "members",
        owner_id="house",
        owner_kind="Household",
        related_id="person",
        related_kind="Person",
        **kwargs,
    )


def test_role_construction_analyzes_artifact_once_per_batch(monkeypatch):
    artifact = _artifact()
    walks = []
    initialize = relation_binding._ArtifactRelations.__init__

    def counted(self, program):
        walks.append(program)
        return initialize(self, program)

    monkeypatch.setattr(relation_binding._ArtifactRelations, "__init__", counted)
    for index in range(120):
        assert relation_binding.relation_tuple(
            artifact,
            "members",
            owner_id="house",
            owner_kind="Household",
            related_id=f"person-{index}",
            related_kind="Person",
        ) == [f"person-{index}", "house"]
    # One snapshot analysis serves every row.
    assert len(walks) == 1


@pytest.mark.parametrize("size", [40, 120])
def test_producer_and_engine_batch_analysis_count_does_not_grow_with_cases(
    monkeypatch,
    tmp_path,
    size,
):
    artifact = _artifact()
    path = tmp_path / "members.compiled.json"
    path.write_text(json.dumps(artifact))
    walks = []
    original = relation_binding._ArtifactRelations.__init__

    def counted(self, program):
        walks.append(program)
        return original(self, program)

    monkeypatch.setattr(relation_binding._ArtifactRelations, "__init__", counted)
    cases = [
        Case(
            str(index),
            "2026-01",
            entities=tuple(Entity(str(person), "Person") for person in range(3)),
        )
        for index in range(size)
    ]
    projected = generic_inputs.attach_generic_inputs(
        cases,
        compiled_program_path=path,
        member_relation="members",
        load_default_mapping=False,
    )
    # Owner discovery and construction share one analysis.
    assert len(walks) == 1

    def fake_run(command, **kwargs):
        request = json.loads(kwargs["input"])
        assert len(request["dataset"]["relations"]) == 3 * size
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "results": [{"outputs": {}} for _ in cases],
                }
            ),
            stderr="",
        )

    adapter = runner.AxiomRulesRunner(
        binary_path=tmp_path / "engine", subprocess_run=fake_run
    )
    assert len(adapter._run_case_batch_once(projected, ["count"], path)) == size
    # The separately loaded runtime artifact needs one constructor analysis.
    assert len(walks) == 2


def test_constructor_cache_observes_in_place_artifact_mutation():
    artifact = _artifact()
    assert _tuple(artifact) == ["person", "house"]
    expression = artifact["program"]["derived"][0]["expr"]
    expression.update(current_slot=0, related_slot=1)
    artifact["program"]["relations"][0]["slot_entities"].reverse()
    assert _tuple(artifact) == ["house", "person"]


def _replace_relation_containers(artifact, replacement):
    """Detach schemas without changing the artifact's content."""
    program = artifact["program"]
    if replacement == "program":
        artifact["program"] = deepcopy(program)
    elif replacement == "relations":
        program["relations"] = deepcopy(program["relations"])
    else:
        program["relations"][:] = [deepcopy(schema) for schema in program["relations"]]


@pytest.mark.parametrize("replacement", ["program", "relations", "schemas"])
@settings(deadline=None)
@given(owner_slot=st.integers(0, 1))
def test_constructor_cache_ignores_detached_schema_name_mutation(
    replacement, owner_slot
):
    artifact = _artifact(owner_slot, owner="Person", member="Person", typed=True)
    detached_schema = artifact["program"]["relations"][0]
    before = deepcopy(artifact)
    arguments = {
        "owner_id": "owner",
        "owner_kind": "Person",
        "related_id": "related",
        "related_kind": "Person",
        "legacy_owner_slot": 1 - owner_slot,
    }
    expected = ["owner", "related"] if owner_slot == 0 else ["related", "owner"]
    assert relation_binding.relation_tuple(artifact, "members", **arguments) == expected

    _replace_relation_containers(artifact, replacement)
    detached_schema["name"] = "detached-members"
    assert artifact == before
    with patch.object(
        relation_binding,
        "_artifact_relation_analysis",
        side_effect=relation_binding._ArtifactRelations,
    ):
        assert (
            relation_binding.relation_tuple(artifact, "members", **arguments)
            == expected
        )
    assert relation_binding.relation_tuple(artifact, "members", **arguments) == expected


@pytest.mark.parametrize("replacement", ["program", "relations", "schemas"])
@settings(deadline=None)
@given(detached_arity=st.integers(3, 10))
def test_owner_kind_cache_ignores_detached_schema_arity_mutation(
    replacement, detached_arity
):
    artifact = _artifact(typed=True)
    detached_schema = {
        "name": "other-members",
        "arity": 2,
        "slot_entities": ["Household", "Person"],
    }
    artifact["program"]["relations"].append(detached_schema)
    before = deepcopy(artifact)
    arguments = {"default_owner_kind": "TaxUnit", "related_kind": "Person"}
    assert (
        relation_binding.relation_owner_kind(artifact, "members", **arguments)
        == "Household"
    )

    _replace_relation_containers(artifact, replacement)
    detached_schema["arity"] = detached_arity
    assert artifact == before
    with patch.object(
        relation_binding,
        "_artifact_relation_analysis",
        side_effect=relation_binding._ArtifactRelations,
    ):
        assert (
            relation_binding.relation_owner_kind(
                artifact,
                "other-members",
                **arguments,
            )
            == "Household"
        )
    assert (
        relation_binding.relation_owner_kind(
            artifact,
            "other-members",
            **arguments,
        )
        == "Household"
    )


def test_constructor_aliases_reuse_the_same_analysis(monkeypatch):
    artifact = _artifact()
    artifact["program"]["derived"][0]["id"] = "us:statutes/7/2012/j#count"
    calls = []
    original = relation_binding._ArtifactRelations.__init__

    def counted(self, program):
        calls.append(program)
        return original(self, program)

    monkeypatch.setattr(relation_binding._ArtifactRelations, "__init__", counted)
    assert _tuple(artifact) == ["person", "house"]
    assert relation_binding.relation_tuple(
        artifact,
        "us:statutes/7/2012/j#relation.members",
        owner_id="house",
        owner_kind="Household",
        related_id="person",
        related_kind="Person",
    ) == ["person", "house"]
    assert len(calls) == 1


@settings(deadline=None)
@given(
    owner_slot=st.integers(0, 1),
    namespaces=st.lists(st.integers(), min_size=2, max_size=30, unique=True),
)
def test_constructor_aliases_share_one_expected_kind_cache_entry(
    owner_slot, namespaces
):
    artifact = _artifact(owner_slot)
    schema = artifact["program"]["relations"][0]
    artifact["program"]["derived"][0]["id"] = "us:statutes/7/2012/j#count"
    before = deepcopy(artifact)
    aliases = [
        "members",
        *(
            f"us:statutes/test/{abs(namespace)}#relation.members"
            for namespace in namespaces
        ),
    ]
    expected = ["house", "person"] if owner_slot == 0 else ["person", "house"]
    for alias in aliases:
        assert (
            relation_binding.relation_tuple(
                artifact,
                alias,
                owner_id="house",
                owner_kind="Household",
                related_id="person",
                related_kind="Person",
            )
            == expected
        )

    entry = relation_binding._ARTIFACT_RELATION_CACHE[id(artifact)]
    analysis = entry.analysis
    assert set(analysis._expected_by_name) == {schema["name"]}
    assert artifact == before


def test_constructor_cache_retains_bounded_artifacts(monkeypatch):
    monkeypatch.setattr(relation_binding, "_MAX_CACHED_ARTIFACTS", 2)
    for _ in range(3):
        artifact = _artifact(typed=False)
        for kind in ("Person", "Payment", "TaxUnit"):
            relation_binding.relation_tuple(
                artifact,
                "members",
                owner_id="house",
                owner_kind="Household",
                related_id="member",
                related_kind=kind,
            )
    cache = relation_binding._ARTIFACT_RELATION_CACHE
    assert len(cache) == 2
    assert all(
        isinstance(entry.analysis, relation_binding._ArtifactRelations)
        for entry in cache.values()
    )


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
    owner,
    member,
    owner_slot,
    legacy_owner_slot,
    typed,
    inverse,
):
    artifact = _artifact(owner_slot, owner, member, typed)
    if inverse:
        artifact["program"]["derived"].append(
            {
                "name": "inverse-count",
                "entity": member,
                "expr": {
                    "kind": "count_related",
                    "relation": "members",
                    "current_slot": 1 - owner_slot,
                    "related_slot": owner_slot,
                },
            }
        )
    before = deepcopy(artifact)
    arguments = {
        "owner_id": "owner",
        "owner_kind": owner,
        "related_id": "member",
        "related_kind": member,
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
            artifact,
            "members",
            default_owner_kind=owner,
            related_kind=member,
        ),
    ]
    for operation in operations:
        expected = outcome(operation)
        assert outcome(operation) == expected
        assert outcome(operation) == expected
        with patch.object(
            relation_binding,
            "_artifact_relation_analysis",
            side_effect=relation_binding._ArtifactRelations,
        ):
            assert outcome(operation) == expected
    assert artifact == before
