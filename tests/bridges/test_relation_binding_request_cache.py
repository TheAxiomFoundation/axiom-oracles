"""Request construction pays for program validation once, independent of tuples."""

from copy import deepcopy
from unittest.mock import patch

import pytest

from axiom_oracles.bridges import relation_binding


class _CountedProgram(dict):
    comparisons = 0

    def __ne__(self, other):
        type(self).comparisons += 1
        return super().__ne__(other)


def _artifact():
    return {
        "program": _CountedProgram(
            relations=[
                {
                    "name": "members",
                    "arity": 2,
                    "slot_entities": ["Household", "Person"],
                }
            ]
        )
    }


def _request(size, *, roles=True):
    return {
        "dataset": {
            "inputs": [
                {"entity_id": "house", "entity": "Household"},
                {"entity_id": "person", "entity": "Person"},
            ],
            "relations": [
                {
                    "name": "members",
                    "tuple": ["person", "house"],
                    **(
                        {
                            "roles": {
                                "owner_id": "house",
                                "owner_kind": "Household",
                                "related_id": "person",
                                "related_kind": "Person",
                            }
                        }
                        if roles or index % 2
                        else {}
                    ),
                }
                for index in range(size)
            ],
        }
    }


@pytest.mark.parametrize("size", [1, 120, 1000])
@pytest.mark.parametrize("roles", [False, True], ids=["mixed", "roles"])
def test_bind_request_revalidates_program_once_regardless_of_tuple_count(size, roles):
    artifact = _artifact()
    request = _request(size, roles=roles)
    before = deepcopy(request)
    # Warm the cache: the regression was repeated deep comparisons, even when
    # no new _ArtifactRelations instance was constructed.
    relation_binding.bind_request_relations(request, artifact)
    _CountedProgram.comparisons = 0
    with patch.object(
        relation_binding,
        "_artifact_relation_analysis",
        wraps=relation_binding._artifact_relation_analysis,
    ) as analyze:
        bound = relation_binding.bind_request_relations(request, artifact)
    assert analyze.call_count == 1
    assert _CountedProgram.comparisons == 1
    assert all(
        record["tuple"] == ["house", "person"]
        for record in bound["dataset"]["relations"]
    )
    assert request == before


def test_bind_request_reanalyzes_program_mutated_between_calls():
    artifact = _artifact()
    request = _request(120)
    with patch.object(
        relation_binding,
        "_ArtifactRelations",
        wraps=relation_binding._ArtifactRelations,
    ) as analyze:
        first = relation_binding.bind_request_relations(request, artifact)
        assert analyze.call_count == 1
        artifact["program"]["relations"][0]["slot_entities"].reverse()
        second = relation_binding.bind_request_relations(request, artifact)
        assert analyze.call_count == 2
    assert first["dataset"]["relations"][0]["tuple"] == ["house", "person"]
    assert second["dataset"]["relations"][0]["tuple"] == ["person", "house"]


def test_request_scoped_constructor_shares_snapshot_and_revalidates_next_request():
    artifact = _artifact()
    roles = _request(1)["dataset"]["relations"][0]["roles"]
    first = relation_binding.RelationBinder(artifact)
    _CountedProgram.comparisons = 0
    for _ in range(120):
        assert (
            first.owner_kind(
                "members", default_owner_kind="Household", related_kind="Person"
            )
            == "Household"
        )
        assert first.tuple("members", **roles) == ["house", "person"]
    assert _CountedProgram.comparisons == 0
    artifact["program"]["relations"][0]["slot_entities"].reverse()
    # The existing request holds its detached snapshot. The next construction
    # boundary validates the changed program before serving any tuples.
    second = relation_binding.RelationBinder(artifact)
    assert _CountedProgram.comparisons == 1
    assert second.tuple("members", **roles) == ["person", "house"]
    assert first.tuple("members", **roles) == ["house", "person"]
