"""Differential regressions against the optional #190 strict engine.

Set AXIOM_STRICT_RELATION_ENGINE_BIN to the reference engine. The inline
programs exercise its serialized expression surface directly; the missing
member regression also compiles RuleSpec and runs the generic adapter.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess

import pytest

from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
from axiom_oracles.bridges.input_binding import bind_typed_input_entities
from axiom_oracles.bridges.relation_binding import bind_request_relations
from axiom_oracles.core.case import Case


_INTERVAL = {"start": "2026-01-01", "end": "2026-12-31"}
_PERIOD = {**_INTERVAL, "period_kind": "tax_year"}
_BASE = "us:policies/review/min"


@pytest.fixture(scope="module")
def strict_engine():
    value = os.environ.get("AXIOM_STRICT_RELATION_ENGINE_BIN")
    if not value or not Path(value).is_file():
        pytest.skip("AXIOM_STRICT_RELATION_ENGINE_BIN must point to a live engine")
    return Path(value).resolve()


def _integer(value):
    return {"kind": "literal", "value": {"kind": "integer", "value": value}}


def _comparison(left, right=None):
    return {
        "kind": "comparison", "op": "eq", "left": left,
        "right": _integer(1) if right is None else right,
    }


def _indicator(condition):
    return {
        "kind": "if", "condition": condition,
        "then_expr": _integer(1), "else_expr": _integer(0),
    }


def _member(relation, current_slot):
    return {
        "kind": "relation_member", "relation": relation,
        "current_slot": current_slot, "related_slot": 1 - current_slot,
    }


def _count(relation="members", current_slot=1, **children):
    return {
        "kind": "count_related", "relation": relation,
        "current_slot": current_slot, "related_slot": 1 - current_slot,
        **children,
    }


def _rule(name, expr, *, entity="TaxUnit", judgment=False):
    return {
        "name": name, "entity": entity,
        "dtype": "judgment" if judgment else "integer",
        "semantics": "judgment" if judgment else "scalar", "expr": expr,
    }


def _request(program, relations):
    return {
        "program": program, "mode": "explain",
        "dataset": {
            "inputs": [
                {
                    "name": "label", "entity": kind, "entity_id": entity_id,
                    "interval": _INTERVAL,
                    "value": {"kind": "integer", "value": 1},
                }
                for kind, entity_id in [("TaxUnit", "tax"), ("Person", "person")]
            ],
            "relations": [
                {"name": name, "tuple": ids, "interval": _INTERVAL}
                for name, ids in relations
            ],
        },
        "queries": [{"entity_id": "tax", "period": _PERIOD, "outputs": ["count"]}],
    }


def _markers():
    return [
        _rule("tax_marker", {"kind": "input", "name": "label"}),
        _rule("person_marker", {"kind": "input", "name": "label"}, entity="Person"),
    ]


def _predicate_fixture(predicate):
    program = {
        "relations": [
            {"name": "source", "arity": 2, "slot_entities": ["Person", "TaxUnit"]},
            {"name": "eligible", "arity": 2, "slot_entities": ["TaxUnit", "Person"]},
            {
                "name": "filtered", "arity": 2,
                "slot_entities": ["Person", "TaxUnit"],
                "derivation": {
                    "source_relation": "source", "current_slot": 1,
                    "related_slot": 0, "slot_entities": ["Person", "TaxUnit"],
                    "predicate": predicate,
                },
            },
        ],
        "derived": [_rule("count", _count("filtered")), *_markers()],
    }
    return _request(program, [("source", ["person", "tax"]), ("eligible", ["tax", "person"])])


def _run(binary, request, artifact_path=None):
    arguments = [str(binary), "run"] if artifact_path is None else [
        str(binary), "run-compiled", "--artifact", str(artifact_path),
    ]
    return subprocess.run(
        arguments, input=json.dumps(request), capture_output=True, text=True,
        check=False, timeout=60,
    )


def _result_number(result, output="count"):
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    return response["results"][0]["outputs"][output]["value"]["value"]


def _assert_strict_count(binary, request, expected=1, artifact_path=None, output="count"):
    assert "relation_binding" not in request
    result = _run(binary, request, artifact_path)
    assert _result_number(result, output) == expected
    assert json.loads(result.stdout)["metadata"]["relation_binding"] == "strict"


@pytest.mark.parametrize("mode", ["explain", "fast"])
@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("wrapper", ["if_condition", "then_branch", "else_branch", "arithmetic"])
def test_scalar_membership_binding_matches_engine_consumed_order(
    strict_engine, mode, current_slot, wrapper,
):
    indicator = _indicator(_member("eligible", current_slot))
    if wrapper == "then_branch":
        indicator = {
            "kind": "if", "condition": _comparison(_integer(1)),
            "then_expr": indicator, "else_expr": _integer(0),
        }
    elif wrapper == "else_branch":
        indicator = {
            "kind": "if", "condition": _comparison(_integer(0)),
            "then_expr": _integer(0), "else_expr": indicator,
        }
    elif wrapper == "arithmetic":
        indicator = {
            "kind": "max", "items": [_integer(0), {
                "kind": "min", "items": [_integer(1), {
                    "kind": "ceil", "value": {"kind": "floor", "value": {
                        "kind": "sub", "left": {
                            "kind": "div", "left": {
                                "kind": "mul", "left": {
                                    "kind": "add", "items": [indicator, _integer(0)],
                                }, "right": _integer(1),
                            }, "right": _integer(1),
                        }, "right": _integer(0),
                    }},
                }],
            }],
        }
    request = _predicate_fixture(_comparison(indicator))
    request["mode"] = mode
    reference = deepcopy(request)
    consumed = ["tax", "person"] if current_slot == 0 else ["person", "tax"]
    reference["dataset"]["relations"][1]["tuple"] = consumed
    _assert_strict_count(strict_engine, reference)

    bound = bind_request_relations(request, {"program": request["program"]})
    assert bound == reference
    _assert_strict_count(strict_engine, bound)

    reversed_request = deepcopy(reference)
    reversed_request["dataset"]["relations"][1]["tuple"].reverse()
    rejected = _run(strict_engine, reversed_request)
    assert rejected.returncode != 0
    assert "strict dataset relation entity validation failed" in rejected.stderr
    assert "dataset relation `eligible` tuple slot" in rejected.stderr
    # Observe consumption independently of the strict binding diagnostics.
    reversed_request["relation_binding"] = "lenient"
    assert _result_number(_run(strict_engine, reversed_request)) == 0


@pytest.mark.parametrize("site", ["judgment", "if_condition", "where", "nested_where", "no_match_pattern"])
def test_nonexecuted_membership_and_patterns_do_not_change_engine_orientation(
    strict_engine, site,
):
    program = {
        "relations": [{"name": "members", "arity": 2, "slot_entities": ["TaxUnit", "Person"]}],
        "derived": [_rule("count", _count()), *_markers()],
    }
    relations = [("members", ["person", "tax"])]
    if site == "no_match_pattern":
        # Only the fallback's subject executes labelled; this also catches
        # dropping the entire no_match node instead of skipping its patterns.
        program["relations"].append({
            "name": "labelled", "arity": 2, "slot_entities": ["TaxUnit", "Person"],
        })
        relations.append(("labelled", ["person", "tax"]))
    if site == "nested_where":
        program["relations"].append({
            "name": "unused_filtered", "arity": 2,
            "slot_entities": ["Person", "TaxUnit"],
            "derivation": {
                "source_relation": "members", "current_slot": 1, "related_slot": 0,
                "slot_entities": ["Person", "TaxUnit"],
                "predicate": _comparison(_count(
                    current_slot=0, where=_member("members", 0),
                )),
            },
        })
    else:
        expr = {
            "judgment": _member("members", 0),
            "if_condition": _indicator(_member("members", 0)),
            "where": _count(where=_member("members", 1)),
            "no_match_pattern": {
                "kind": "no_match", "subject": _count("labelled"),
                "patterns": [_count("labelled", current_slot=0)],
            },
        }[site]
        program["derived"].append(_rule("unused", expr, judgment=site == "judgment"))
    request = _request(program, relations)
    # Engine inference visits all rule bodies, even these unrequested outputs.
    _assert_strict_count(strict_engine, request)
    bound = bind_request_relations(request, {"program": program})
    assert bound == request
    _assert_strict_count(strict_engine, bound)

    wrong = deepcopy(request)
    record = wrong["dataset"]["relations"][1 if site == "no_match_pattern" else 0]
    record["tuple"].reverse()
    rejected = _run(strict_engine, wrong)
    assert rejected.returncode != 0
    assert "strict dataset relation entity validation failed" in rejected.stderr
    assert f"dataset relation `{record['name']}` tuple slot" in rejected.stderr


def test_over_periods_drops_pair_context_like_reference_engine(strict_engine):
    predicate = _comparison({
        "kind": "over_periods", "over": "sum",
        "value": _indicator(_member("eligible", 1)),
    })
    request = _predicate_fixture(predicate)
    bound = bind_request_relations(request, {"program": request["program"]})
    # No evaluator supports this reduction inside a derived predicate, so
    # its membership imposes no orientation and eligible keeps its declaration.
    assert bound == request
    reference = _run(strict_engine, request)
    observed = _run(strict_engine, bound)
    assert reference.returncode != 0
    assert observed.returncode == reference.returncode
    assert observed.stderr == reference.stderr
    assert "over_periods" in observed.stderr
    assert "strict dataset relation entity validation failed" not in observed.stderr


@pytest.fixture(scope="module")
def missing_member_artifact(strict_engine, tmp_path_factory):
    directory = tmp_path_factory.mktemp("relation-missing-member")
    root = directory / "rulespec-us"
    source = root / "us/policies/review/min.yaml"
    source.parent.mkdir(parents=True)
    source.write_text("""format: rulespec/v1
rules:
  - name: members
    kind: data_relation
    data_relation:
      arity: 2
      arguments: [TaxUnit, Person]
  - name: owner_number
    kind: derived
    entity: TaxUnit
    dtype: Integer
    versions:
      - effective_from: 2026-01-01
        formula: number
  - name: eligible
    kind: derived
    entity: Person
    dtype: Judgment
    versions:
      - effective_from: 2026-01-01
        formula: 1 == 1
  - name: member_count
    kind: derived
    entity: TaxUnit
    dtype: Integer
    versions:
      - effective_from: 2026-01-01
        formula: count_where(members, eligible)
""")
    artifact_path = directory / "min.compiled.json"
    compiled = subprocess.run(
        [str(strict_engine), "compile", "--program", str(source),
         "--rulespec-root", str(root), "--output", str(artifact_path)],
        capture_output=True, text=True, check=False, timeout=60,
    )
    assert compiled.returncode == 0, compiled.stderr
    return artifact_path, json.loads(artifact_path.read_text())


@pytest.mark.parametrize("supplied_owner_slot", [0, 1])
@pytest.mark.parametrize("entrypoint", ["binding", "single_runner", "batch_runner"])
def test_unlabelled_member_matches_strict_compiled_engine(
    strict_engine, missing_member_artifact, supplied_owner_slot, entrypoint,
):
    artifact_path, artifact = missing_member_artifact
    ids = ["tax_unit", "child"] if supplied_owner_slot == 0 else ["child", "tax_unit"]
    case = Case(case_id="count", period="2026", metadata={
        "axiom_input_records": [{
            "name": f"{_BASE}#input.number", "entity": "TaxUnit",
            "entity_id": "tax_unit", "value": 0,
        }],
        "axiom_relations": [{"name": f"{_BASE}#relation.members", "tuple": ids}],
    })
    runner = AxiomRulesRunner(compiled_artifact_path=artifact_path, binary_path=strict_engine)
    outputs = [f"{_BASE}#member_count"]
    request = runner._execution_request(case, outputs)
    reference = deepcopy(request)
    reference["dataset"]["relations"][0]["tuple"] = ["tax_unit", "child"]
    _assert_strict_count(strict_engine, reference, artifact_path=artifact_path, output=outputs[0])

    if entrypoint == "binding":
        bound = bind_request_relations(request, artifact)
        assert bound == reference
        _assert_strict_count(strict_engine, bound, artifact_path=artifact_path, output=outputs[0])
    else:
        result = runner._run_case_once(case, outputs, artifact_path) if entrypoint == "single_runner" else (
            runner._run_case_batch_once([case], outputs, artifact_path)[0]
        )
        assert result.errors == ()
        assert result.values[outputs[0]] == 1


@pytest.fixture(scope="module")
def synthetic_entity_artifact(strict_engine, tmp_path_factory):
    directory = tmp_path_factory.mktemp("relation-synthetic-entity")
    root = directory / "rulespec-us"
    source = root / "us/policies/review/synthetic.yaml"
    source.parent.mkdir(parents=True)
    # The reference engine's filtered-entity alias fixture: SnapUnit executes
    # on its structural Household owner and exposes snap_unit as members.
    source.write_text("""format: rulespec/v1
rules:
  - name: member_of_household
    kind: data_relation
    data_relation:
      arity: 2
      arguments: [Person, Household]
  - name: snap_member_eligible
    kind: derived
    entity: Person
    dtype: Judgment
    versions:
      - effective_from: 2025-01-01
        formula: has_ssn
  - name: snap_unit
    kind: derived_relation
    derived_relation:
      arity: 2
      source_relation: member_of_household
      entity: SnapUnit
      member_relation: members
      slot_entities: [Person, Household]
    versions:
      - effective_from: 2025-01-01
        formula: member_of_household and snap_member_eligible
  - name: snap_unit_size
    kind: derived
    entity: SnapUnit
    dtype: Integer
    versions:
      - effective_from: 2025-01-01
        formula: len(members)
  - name: owner_number
    kind: derived
    entity: SnapUnit
    dtype: Integer
    versions:
      - effective_from: 2025-01-01
        formula: number
""")
    artifact_path = directory / "synthetic.compiled.json"
    compiled = subprocess.run(
        [str(strict_engine), "compile", "--program", str(source),
         "--rulespec-root", str(root), "--output", str(artifact_path)],
        capture_output=True, text=True, check=False, timeout=60,
    )
    assert compiled.returncode == 0, compiled.stderr
    artifact = json.loads(artifact_path.read_text())
    relation = next(
        item for item in artifact["program"]["relations"]
        if item["name"] == "us:policies/review/synthetic#relation.snap_unit"
    )
    assert relation["derivation"]["entity"] == "SnapUnit"
    assert relation["derivation"]["slot_entities"] == ["Person", "Household"]
    assert relation["derivation"]["current_slot"] == 1
    size = next(rule for rule in artifact["program"]["derived"] if rule["name"] == "snap_unit_size")
    assert size["entity"] == "SnapUnit"
    return artifact_path, artifact


@pytest.mark.parametrize("specific_labels", [False, True])
def test_synthetic_entity_alias_uses_structural_owner_kind_in_strict_engine(
    strict_engine, synthetic_entity_artifact, specific_labels,
):
    artifact_path, artifact = synthetic_entity_artifact
    base = "us:policies/review/synthetic"
    output = f"{base}#snap_unit_size"
    request = {
        "mode": "explain",
        "dataset": {
            "inputs": [
                {
                    "name": f"{base}#input.number", "entity_id": "household",
                    "entity": "Household" if specific_labels else "Entity",
                    "interval": _INTERVAL, "value": {"kind": "integer", "value": 0},
                },
                {
                    "name": f"{base}#input.has_ssn", "entity_id": "person",
                    "entity": "Person" if specific_labels else "Entity",
                    "interval": _INTERVAL, "value": {"kind": "bool", "value": True},
                },
            ],
            "relations": [{
                "name": f"{base}#relation.member_of_household",
                "tuple": ["household", "person"], "interval": _INTERVAL,
            }],
        },
        "queries": [{"entity_id": "household", "period": _PERIOD, "outputs": [output]}],
    }
    before = deepcopy(request)
    reference = deepcopy(request)
    reference["dataset"]["inputs"][0]["entity"] = "Household"
    reference["dataset"]["inputs"][1]["entity"] = "Person"
    reference["dataset"]["relations"][0]["tuple"] = ["person", "household"]
    _assert_strict_count(strict_engine, reference, artifact_path=artifact_path, output=output)

    bound = bind_request_relations(bind_typed_input_entities(request, artifact), artifact)
    assert request == before
    assert bound == reference
    _assert_strict_count(strict_engine, bound, artifact_path=artifact_path, output=output)
