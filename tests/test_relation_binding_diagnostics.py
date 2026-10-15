"""Production diagnostics preserve every ambiguity, without producer false alarms."""

from copy import deepcopy
import json
import subprocess
import warnings

import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner, _select_candidate_result
from axiom_oracles.bridges.relation_binding import (
    RelationBindingAmbiguityWarning,
    bind_request_relations,
)
from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import ComparisonReportAccumulator
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


def _artifact(slot=0, used=True):
    return {"program": {
        "relations": [{"name": "members", "arity": 2}],
        "derived": [{"name": "n", "entity": "Household", "expr": {
            "kind": "count_related", "relation": "members",
            "current_slot": slot, "related_slot": 1 - slot,
        }}] if used else [],
    }}


def _case(case_id, *, roles=False, repeats=1):
    record = {"name": "members", "tuple": ["member", "owner"]}
    if roles:
        record["roles"] = {
            "owner_id": "owner", "owner_kind": "Household",
            "related_id": "member", "related_kind": "Person",
        }
    return Case(case_id, "2026-01", metadata={
        "axiom_entity_id": "owner", "axiom_relations": [deepcopy(record)] * repeats,
    })


def _runner(tmp_path, artifact, *, returncode=0, invalid_json=False):
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(artifact))
    def run(cmd, **kwargs):
        request = json.loads(kwargs["input"])
        assert all("roles" not in row for row in request["dataset"]["relations"])
        stdout = "invalid" if invalid_json else json.dumps({"results": [
            {"outputs": {"n": {"value": {"kind": "integer", "value": 0}}}}
            for _ in request["queries"]
        ]})
        return subprocess.CompletedProcess(cmd, returncode, stdout, "engine failure")
    return AxiomRulesRunner(binary_path=tmp_path / "engine", subprocess_run=run), path


@pytest.mark.parametrize("batched", [False, True])
@pytest.mark.parametrize("failure", ["none", "engine", "json"])
def test_undetermined_tuples_reach_result_diagnostics(tmp_path, batched, failure):
    adapter, artifact = _runner(tmp_path, _artifact(), returncode=int(failure == "engine"),
                                invalid_json=failure == "json")
    case = _case("probe", repeats=25)
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter("always")
        result = (adapter._run_case_batch_once([case], ["n"], artifact)[0] if batched
                  else adapter._run_case_once(case, ["n"], artifact))
    diagnostics = result.raw["relation_binding_diagnostics"]
    assert diagnostics["count"] == 25
    assert diagnostics["by_relation"] == {"members": 25}
    assert len(diagnostics["samples"]) == 20
    prefix = "case-0::" if batched else ""
    assert diagnostics["samples"][0] == {
        "relation": "members", "tuple": [prefix + "member", prefix + "owner"],
    }
    assert not emitted


@pytest.mark.parametrize("batched", [False, True])
def test_role_materialization_keeps_untyped_order_and_diagnostic(tmp_path, batched):
    adapter, artifact = _runner(tmp_path, _artifact())
    case = _case("probe", roles=True)
    before = deepcopy(case.metadata)
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter("always")
        result = (adapter._run_case_batch_once([case], ["n"], artifact)[0] if batched
                  else adapter._run_case_once(case, ["n"], artifact))
    assert not emitted
    diagnostics = result.raw["relation_binding_diagnostics"]
    assert diagnostics["count"] == 1
    assert diagnostics["by_relation"] == {"members": 1}
    prefix = "case-0::" if batched else ""
    assert diagnostics["samples"] == [{
        "relation": "members", "tuple": [prefix + "member", prefix + "owner"],
    }]
    assert case.metadata == before


@settings(deadline=None)
@given(ids=st.lists(st.text(min_size=1, max_size=10), min_size=2, max_size=2))
def test_unused_untyped_relations_preserve_without_warning(ids):
    request = {"dataset": {"inputs": [], "relations": [{"name": "members", "tuple": ids}]}}
    before = deepcopy(request)
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter("always")
        assert bind_request_relations(request, _artifact(used=False)) == before
    assert not emitted
    assert request == before


def test_repeated_batch_names_count_in_report_provenance(tmp_path):
    adapter, artifact = _runner(tmp_path, _artifact())
    mapping = ProgramMapping(standard="us:test#n", description="count", category="test",
                             comparison="amount", targets={"axiom": "n", "oracle": "n"})
    accumulator = ComparisonReportAccumulator(suite_name="test", population="synthetic",
                                              locales=set(), scope=None, mappings=[mapping])
    for case_id in ("first", "second"):
        cases = [_case(case_id, repeats=25), _case(case_id + "-known", roles=True)]
        results = adapter._run_case_batch_once(cases, ["n"], artifact)
        assert results[1].raw["relation_binding_diagnostics"]["count"] == 1
        comparisons = Comparator([mapping]).compare(
            results, [EngineResult("oracle", case.case_id, {"n": 0}) for case in cases],
        )
        accumulator.add_batch(cases, comparisons)
    report = accumulator.to_dict()
    diagnostics = report["provenance"]["relation_binding_diagnostics"]
    assert diagnostics["count"] == 52
    assert diagnostics["by_relation"] == {"members": 52}
    assert len(diagnostics["samples"]) == 20
    assert diagnostics["samples"] == [{"relation": "members"}] * 20
    path = tmp_path / "report.json"
    accumulator.write_json(path)
    assert json.loads(path.read_text())["provenance"] == report["provenance"]


@settings(deadline=None)
@given(slot=st.integers(0, 1), reversed_tuple=st.booleans())
def test_explicit_roles_never_require_input_identity(slot, reversed_tuple):
    record = deepcopy(_case("probe", roles=True).metadata["axiom_relations"][0])
    if reversed_tuple:
        record["tuple"].reverse()
    request = {"dataset": {"inputs": [], "relations": [record]}}
    before = deepcopy(request)
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter("always")
        bound = bind_request_relations(request, _artifact(slot))
    assert bound["dataset"]["relations"][0]["tuple"] == ["member", "owner"]
    assert len(emitted) == 1
    assert isinstance(emitted[0].message, RelationBindingAmbiguityWarning)
    assert emitted[0].message.relation == "members"
    assert request == before


@pytest.mark.parametrize("valid_selection", [False, True])
def test_candidate_selection_counts_every_execution_ambiguity(valid_selection):
    diagnostics = {"count": 25, "by_relation": {"members": 25}, "samples": [
        {"relation": "members", "tuple": ["member", "owner"]} for _ in range(20)
    ]}
    case = Case("probe", "2026-01", metadata={
        "axiom_result_selection": {"strategy": "min", "output": "n"},
    } if valid_selection else {})
    candidates = [EngineResult("axiom", "probe", {"n": 0}, raw={
        "relation_binding_diagnostics": deepcopy(diagnostics),
    }) for _ in range(2)]
    result = _select_candidate_result("axiom", case, candidates)
    summary = result.raw["relation_binding_diagnostics"]
    assert summary["count"] == 50
    assert summary["by_relation"] == {"members": 50}
    assert len(summary["samples"]) == 20


@pytest.mark.parametrize("matched", [True, False])
@pytest.mark.parametrize("two_queries", [False, True])
def test_tax_execution_ambiguity_reaches_native_report(tmp_path, monkeypatch, matched, two_queries):
    import pandas as pd
    from axiom_oracles.bridges import tax_populace

    root = tmp_path / "rulespec-us"
    root.mkdir()
    program = root / "probe.yaml"
    program.write_text("format: rulespec/v1\nrules: []\n")
    engine_root = tmp_path / "engine"
    binary = engine_root / "target/release/axiom-rules-engine"
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setattr(tax_populace, "_rulespec_repo_alias_parent", lambda _: None)
    monkeypatch.setattr(tax_populace, "_canonical_rulespec_compile_path", lambda path, _: path)
    monkeypatch.setattr(tax_populace.tempfile, "tempdir", str(tmp_path))
    def run(cmd, **kwargs):
        if "compile" in cmd:
            from pathlib import Path
            Path(cmd[cmd.index("--output") + 1]).write_text(json.dumps(_artifact()))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        request = json.loads(kwargs["input"])
        assert "relation_binding_diagnostics" not in request
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"results": [{
            "entity_id": query["entity_id"], "outputs": {"n": {"value": {
                "kind": "integer", "value": 0,
            }}},
        } for query in request["queries"]]}), "")
    monkeypatch.setattr(tax_populace.subprocess, "run", run)
    query_ids = ["tax_unit_1", "member"] if two_queries else ["tax_unit_1"]
    ids = ["member", "tax_unit_1"] if matched else ["unlabelled-a", "unlabelled-b"]
    request = {"dataset": {"inputs": [], "relations": [
        {"name": "members", "tuple": ids} for _ in range(25)
    ]}, "queries": [{"entity_id": entity_id, "outputs": ["n"]} for entity_id in query_ids]}
    before = deepcopy(request)
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter("always")
        results = tax_populace.run_axiom_program(
            program=program, request=request, rulespec_root=root, axiom_rules_path=engine_root,
        )
    assert not emitted
    assert request == before
    assert results[0]["relation_binding_diagnostics"]["count"] == 25
    assert sum(row.get("relation_binding_diagnostics", {}).get("count", 0) for row in results) == 25
    monkeypatch.setattr(tax_populace, "SURFACE_OUTPUTS", {
        "ctc": {"n": {"axiom": "n", "pe": "n"}},
    })
    report = tax_populace.compare_outputs(
        pe_data={"tax_unit_ids": list(range(1, len(query_ids) + 1)), "person_ids": [],
                 "tax_units": pd.DataFrame([{"n": 0}] * len(query_ids)), "persons": pd.DataFrame()},
        axiom_outputs_by_surface={"ctc": results}, tolerance=0, relative_tolerance=0,
    ).to_json()
    assert report["provenance"]["relation_binding_diagnostics"]["count"] == 25


@pytest.mark.parametrize("roles", [False, True])
def test_tax_runtime_without_collector_warns_for_untyped_relation(tmp_path, roles):
    from axiom_oracles.bridges import tax_populace

    record = _case("probe", roles=roles).metadata["axiom_relations"][0]
    request = {
        "dataset": {"inputs": [], "relations": [record]},
        "queries": [{"entity_id": "owner", "outputs": ["n"]}],
    }
    before = deepcopy(request)
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter("always")
        runtime, _ = tax_populace._runtime_axiom_request(
            request, artifact_payload=_artifact(), rulespec_root=tmp_path,
        )
    assert request == before
    assert runtime["dataset"]["relations"][0]["tuple"] == ["member", "owner"]
    assert "roles" not in runtime["dataset"]["relations"][0]
    assert len(emitted) == 1
    assert isinstance(emitted[0].message, RelationBindingAmbiguityWarning)
    assert emitted[0].message.relation == "members"
