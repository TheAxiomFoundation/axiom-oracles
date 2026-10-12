"""Public reports count ambiguity without exposing private relation endpoints."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import warnings

import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import ComparisonReportAccumulator
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


def _registry():
    path = Path(__file__).parents[1] / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("publication_registry", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _mapping():
    return ProgramMapping(
        standard="us:test#n", description="count", category="test",
        comparison="amount", targets={"axiom": "n", "oracle": "n"},
    )


def _accumulator(mapping):
    return ComparisonReportAccumulator(
        suite_name="private-endpoints", population="synthetic", locales=set(),
        scope=None, mappings=[mapping], include_inputs=False,
    )


def test_actual_dashboard_json_omits_private_and_hostile_relation_endpoints(
    tmp_path, monkeypatch,
):
    private = "SSN-123-45-6789"
    hostile = "</script><img src=x onerror=alert(1)>"
    artifact = {"program": {
        "relations": [{"name": "members", "arity": 2}, {"name": "unused", "arity": 2}],
        "derived": [{"name": "n", "entity": "Household", "expr": {
            "kind": "count_related", "relation": "members",
            "current_slot": 0, "related_slot": 1,
        }}],
    }}
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(json.dumps(artifact))

    def run(cmd, **kwargs):
        request = json.loads(kwargs["input"])
        assert all("roles" not in row for row in request["dataset"]["relations"])
        assert "relation_binding_diagnostics" not in json.dumps(request)
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"results": [
            {"outputs": {"n": {"value": {"kind": "integer", "value": 0}}}}
            for _ in request["queries"]
        ]}), "")

    adapter = AxiomRulesRunner(binary_path=tmp_path / "engine", subprocess_run=run)
    mapping = _mapping()
    accumulator = _accumulator(mapping)
    raw_evidence = []
    for batch in range(2):
        relations = [{"name": "members", "tuple": [private, hostile]} for _ in range(3)]
        relations.extend([
            {"name": "members", "tuple": ["member", "owner"], "roles": {
                "owner_id": "owner", "owner_kind": "Household",
                "related_id": "member", "related_kind": "Person",
            }},
            {"name": "unused", "tuple": ["unused-a", "unused-b"]},
        ])
        case = Case(f"public-case-{batch}", "2026-01", metadata={
            "axiom_relations": relations,
        })
        before = deepcopy(case.metadata)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = adapter._run_case_batch_once([case], ["n"], artifact_path)[0]
        assert not caught
        assert case.metadata == before
        diagnostics = result.raw["relation_binding_diagnostics"]
        assert diagnostics["count"] == 3
        assert diagnostics["samples"][0]["tuple"] == [
            "case-0::" + private, "case-0::" + hostile,
        ]
        raw_evidence.append((result.raw, deepcopy(result.raw)))
        comparisons = Comparator([mapping]).compare(
            [result], [EngineResult("oracle", case.case_id, {"n": 0})],
        )
        accumulator.add_batch([case], comparisons)

    report = accumulator.to_dict()
    assert "axiom_relations" not in report["cases"][0]["metadata"]
    full_path = tmp_path / "full.json"
    accumulator.write_json(full_path)
    registry = _registry()
    monkeypatch.setattr(registry, "DASHBOARD_DATA_DIR", tmp_path / "public" / "data")
    monkeypatch.setattr(registry, "_merge_dispositions", lambda row: row)
    registry._write_dashboard_report(report, "private-endpoints.json")
    dashboard_path = registry.DASHBOARD_DATA_DIR / "private-endpoints.json"

    for path in (full_path, dashboard_path):
        body = path.read_text()
        assert private not in body
        assert hostile not in body
        assert json.loads(body)["provenance"]["relation_binding_diagnostics"] == {
            "count": 6, "by_relation": {"members": 6},
            "samples": [{"relation": "members"}] * 6,
        }
    assert all(raw == before for raw, before in raw_evidence)


@pytest.mark.parametrize("container", ["provenance", "dataset_identity"])
def test_dashboard_writer_redacts_preexisting_diagnostic_samples(
    tmp_path, monkeypatch, container,
):
    registry = _registry()
    private = "SSN-123-45-6789"
    hostile = "</script><img src=x onerror=alert(1)>"
    report = {
        "suite": "preexisting-diagnostics", "cases": [], "mismatches": [],
        "summary": {"mismatch_count": 0}, container: {
            "relation_binding_diagnostics": {
                "count": 1, "by_relation": {"members": 1}, "samples": [
                    {"relation": "members", "tuple": [private, hostile],
                     "case_id": private, "unexpected_metadata": hostile},
                ],
            },
        },
    }
    before = deepcopy(report)
    monkeypatch.setattr(registry, "DASHBOARD_DATA_DIR", tmp_path / "public" / "data")
    monkeypatch.setattr(registry, "_merge_dispositions", lambda row: row)

    registry._write_dashboard_report(report, "preexisting-diagnostics.json")

    path = registry.DASHBOARD_DATA_DIR / "preexisting-diagnostics.json"
    body = path.read_text()
    assert private not in body
    assert hostile not in body
    assert json.loads(body)[container]["relation_binding_diagnostics"] == {
        "count": 1, "by_relation": {"members": 1}, "samples": [{"relation": "members"}],
    }
    assert report == before


@pytest.mark.parametrize("with_observation", [False, True])
def test_tax_report_preserves_legacy_positional_observations_and_errors(with_observation):
    from axiom_oracles.bridges.tax_populace import TaxComparisonReport

    identity = {"population": "synthetic"}
    observations = (
        [{"case_id": "tax_unit_1", "engine": "axiom", "value": 10}]
        if with_observation else []
    )
    errors = [{"case_id": "tax_unit_1", "engine": "axiom", "error": "stopped"}]
    before = deepcopy((identity, observations, errors))

    report = TaxComparisonReport(1, 0, 1, [], [], [], identity, observations, errors)
    published = report.to_json()

    assert published["dataset_identity"] == identity
    assert published["observed_outputs"] == observations
    assert published["errors"] == errors
    assert "provenance" not in published
    assert (identity, observations, errors) == before


@settings(max_examples=24, deadline=None)
@given(
    values=st.lists(st.integers(), max_size=5),
    error_messages=st.lists(st.text(max_size=40), min_size=1, max_size=5),
    with_diagnostics=st.booleans(),
)
def test_tax_report_positional_ledgers_are_independent_of_keyword_diagnostics(
    values, error_messages, with_diagnostics,
):
    from axiom_oracles.bridges.tax_populace import TaxComparisonReport

    observations = [{"case_id": "tax_unit_1", "value": value} for value in values]
    errors = [{"case_id": "tax_unit_1", "error": error} for error in error_messages]
    diagnostics = {"count": 1, "by_relation": {"members": 1}, "samples": [
        {"relation": "members", "tuple": ["member", "owner"]},
    ]}
    before = deepcopy((observations, errors, diagnostics))
    kwargs = {"relation_binding_diagnostics": diagnostics} if with_diagnostics else {}
    report = TaxComparisonReport(1, 0, len(values), [], [], [], None,
                                 observations, errors, **kwargs)

    published = json.loads(json.dumps(report.to_json(), allow_nan=False))

    assert published["observed_outputs"] == observations
    assert published["errors"] == errors
    if with_diagnostics:
        assert published["provenance"]["relation_binding_diagnostics"] == {
            "count": 1, "by_relation": {"members": 1}, "samples": [{"relation": "members"}],
        }
    else:
        assert "provenance" not in published
    assert (observations, errors, diagnostics) == before


def test_tax_report_serialization_redacts_diagnostics_and_keeps_execution_evidence():
    from axiom_oracles.bridges.tax_populace import TaxComparisonReport

    private = "SSN-123-45-6789"
    hostile = "</script><img src=x onerror=alert(1)>"
    diagnostics = {"count": 1, "by_relation": {"members": 1}, "samples": [
        {"relation": "members", "tuple": [private, hostile]},
    ]}
    before = deepcopy(diagnostics)
    report = TaxComparisonReport(
        compared_tax_units=1, compared_persons=0, compared_values=1,
        mismatches=[], output_summary=[], projection_notes=[],
        relation_binding_diagnostics=diagnostics,
        observed_outputs=[{"case_id": "public-case", "value": float("nan")}],
        errors=[{"case_id": "public-case", "error": float("nan")}],
    )

    published = report.to_json()

    assert published["provenance"]["relation_binding_diagnostics"] == {
        "count": 1, "by_relation": {"members": 1}, "samples": [{"relation": "members"}],
    }
    assert published["observed_outputs"] == [{"case_id": "public-case", "value": None}]
    assert published["errors"] == [{"case_id": "public-case", "error": True}]
    body = json.dumps(published, allow_nan=False)
    assert private not in body
    assert hostile not in body
    assert diagnostics == before


@settings(max_examples=24, deadline=None)
@given(endpoints=st.lists(st.text(max_size=40), min_size=2, max_size=2),
       count=st.integers(min_value=1, max_value=50))
def test_report_diagnostic_provenance_is_independent_of_endpoint_identifiers(
    endpoints, count,
):
    mapping = _mapping()
    accumulator = _accumulator(mapping)
    diagnostics = {"count": count, "by_relation": {"members": count}, "samples": [
        {"relation": "members", "tuple": endpoints} for _ in range(min(count, 20))
    ]}
    raw = {"relation_binding_diagnostics": diagnostics}
    before = deepcopy(raw)
    case = Case("public-case", "2026-01")
    comparisons = Comparator([mapping]).compare(
        [EngineResult("axiom", case.case_id, {"n": 0}, raw=raw)],
        [EngineResult("oracle", case.case_id, {"n": 0})],
    )
    accumulator.add_batch([case], comparisons)
    serialized = json.loads(json.dumps(accumulator.to_dict()))
    assert serialized["provenance"]["relation_binding_diagnostics"] == {
        "count": count, "by_relation": {"members": count},
        "samples": [{"relation": "members"}] * min(count, 20),
    }
    assert raw == before


@pytest.mark.parametrize("name, public_name", [
    ("urn:private:SSN-123-45-6789#members", "members"),
    ("relation.members", "members"),
    ("</script><img src=x onerror=alert(1)>", "redacted_relation"),
    ("x" * 129, "redacted_relation"),
])
def test_report_diagnostics_publish_safe_relation_names(name, public_name):
    mapping = _mapping()
    accumulator = _accumulator(mapping)
    diagnostics = {"count": 3, "by_relation": {name: 2, "members": 1}, "samples": [
        {"relation": name, "tuple": ["private-a", "private-b"]},
    ]}
    case = Case("public-case", "2026-01")
    comparisons = Comparator([mapping]).compare(
        [EngineResult("axiom", case.case_id, {"n": 0}, raw={
            "relation_binding_diagnostics": diagnostics,
        })],
        [EngineResult("oracle", case.case_id, {"n": 0})],
    )
    accumulator.add_batch([case], comparisons)
    expected_counts = {public_name: 2}
    expected_counts["members"] = expected_counts.get("members", 0) + 1
    assert accumulator.to_dict()["provenance"]["relation_binding_diagnostics"] == {
        "count": 3, "by_relation": expected_counts,
        "samples": [{"relation": public_name}],
    }
