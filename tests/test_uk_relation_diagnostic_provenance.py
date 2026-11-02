"""UK source reports preserve ambiguity counts without publishing endpoints."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import warnings

from hypothesis import given, settings, strategies as st
import pytest

from axiom_oracles.bridges import efrs_uk, tax_populace
from axiom_oracles.bridges.relation_binding import RELATION_BINDING_SAMPLE_LIMIT


PRIVATE_ENDPOINT = "UK-PRIVATE-SSN-123-45-6789"
HOSTILE_ENDPOINT = "</script><img src=x onerror=alert(1)>"


def _registry():
    path = Path(__file__).parents[1] / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("uk_diagnostic_registry", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _pe_data():
    return {
        "person_ids": [1],
        "persons": [{
            "person_id": 1,
            "personal_allowance": 0,
            "self_employment_income": 1,
            "ni_class_4_main": 0,
        }],
    }


def _compare(outputs):
    return efrs_uk.compare_outputs(
        pe_data=_pe_data(),
        axiom_outputs_by_surface=outputs,
        tolerance=0,
        relative_tolerance=0,
    ).to_json()


def _result(surface, count):
    return {
        "entity_id": "person_1",
        "outputs": {
            spec["axiom"]: {"value": {"kind": "integer", "value": 0}}
            for spec in efrs_uk.SURFACE_SPECS[surface].outputs.values()
        },
        "relation_binding_diagnostics": {
            "count": count,
            "by_relation": {"members": count},
            "samples": [
                {"relation": "members", "tuple": [PRIVATE_ENDPOINT, HOSTILE_ENDPOINT]}
                for _ in range(min(count, RELATION_BINDING_SAMPLE_LIMIT))
            ],
        },
    }


def _assert_public_diagnostics(report, count):
    diagnostics = report["provenance"]["relation_binding_diagnostics"]
    assert diagnostics["count"] == count
    assert diagnostics["by_relation"] == {"members": count}
    assert len(diagnostics["samples"]) == min(count, RELATION_BINDING_SAMPLE_LIMIT)
    assert all(sample == {"relation": "members"} for sample in diagnostics["samples"])
    encoded = json.dumps(report)
    assert PRIVATE_ENDPOINT not in encoded
    assert HOSTILE_ENDPOINT not in encoded


def test_uk_native_ambiguity_reaches_source_report_without_private_endpoints(
    tmp_path, monkeypatch,
):
    output = efrs_uk.PERSONAL_ALLOWANCE_OUTPUTS["personal_allowance"]["axiom"]
    artifact = {"program": {
        "relations": [{"name": "members", "arity": 2}],
        "derived": [{
            "name": output,
            "entity": "Person",
            "expr": {
                "kind": "count_related", "relation": "members",
                "current_slot": 0, "related_slot": 1,
            },
        }],
    }}
    request = {
        "dataset": {"inputs": [], "relations": [{
            "name": "members", "tuple": [PRIVATE_ENDPOINT, HOSTILE_ENDPOINT],
        }]},
        "queries": [{"entity_id": "person_1", "outputs": [output]}],
    }
    before = deepcopy(request)
    rulespec_root = tmp_path / "rulespec-uk"
    rulespec_root.mkdir()
    program = rulespec_root / "probe.yaml"
    program.write_text("format: rulespec/v1\nrules: []\n")
    engine = tmp_path / "engine"
    binary = engine / "target" / "release" / "axiom-rules-engine"
    binary.parent.mkdir(parents=True)
    binary.touch()
    wire_requests = []

    def run(cmd, **kwargs):
        if cmd[0] == "git":
            return subprocess.CompletedProcess(cmd, 1, "", "")
        if "compile" in cmd:
            Path(cmd[cmd.index("--output") + 1]).write_text(json.dumps(artifact))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        wire_request = json.loads(kwargs["input"])
        wire_requests.append(wire_request)
        return subprocess.CompletedProcess(cmd, 0, json.dumps({
            "results": [{
                "entity_id": query["entity_id"],
                "outputs": {
                    name: {"value": {"kind": "integer", "value": 0}}
                    for name in query["outputs"]
                },
            } for query in wire_request["queries"]],
        }), "")

    monkeypatch.setattr(tax_populace, "_rulespec_repo_alias_parent", lambda _: None)
    monkeypatch.setattr(tax_populace, "_canonical_rulespec_compile_path", lambda p, _: p)
    monkeypatch.setattr(tax_populace.subprocess, "run", run)
    monkeypatch.setattr(tax_populace.tempfile, "tempdir", str(tmp_path))
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter("always")
        results = efrs_uk.run_axiom_surface(
            program=program, request=request, rulespec_root=rulespec_root,
            axiom_rules_path=engine, surface="personal-allowance",
        )

    assert not emitted
    raw = results[0]["relation_binding_diagnostics"]
    assert raw["count"] == 1
    assert raw["samples"][0]["tuple"] == [PRIVATE_ENDPOINT, HOSTILE_ENDPOINT]
    raw_before = deepcopy(raw)
    report = _compare({"personal-allowance": results})
    assert report["compared_values"] == 1
    _assert_public_diagnostics(report, 1)
    assert raw == raw_before
    assert request == before
    assert len(wire_requests) == 1
    assert "relation_binding_diagnostics" not in json.dumps(wire_requests)


@pytest.mark.parametrize("report_count", [1, 2])
def test_uk_surface_report_merge_retains_counts_and_bounds_public_samples(report_count):
    source = _compare({"personal-allowance": [_result("personal-allowance", 17)]})
    reports = [deepcopy(source) for _ in range(report_count)]
    before = deepcopy(reports)
    merged = _registry()._merge_uk_efrs_reports(reports)
    _assert_public_diagnostics(merged, 17 * report_count)
    assert merged["compared_values"] == report_count
    assert reports == before


@settings(max_examples=20, deadline=None)
@given(first=st.integers(1, 100), second=st.integers(1, 100))
def test_uk_diagnostic_counts_are_additive_across_surfaces_and_report_merges(first, second):
    allowance = _result("personal-allowance", first)
    national_insurance = _result("national-insurance-class-4", second)
    before = deepcopy([allowance, national_insurance])
    report = _compare({
        "personal-allowance": [allowance],
        "national-insurance-class-4": [national_insurance],
    })
    _assert_public_diagnostics(report, first + second)
    assert report["compared_values"] == 2
    separate = [
        _compare({"personal-allowance": [allowance]}),
        _compare({"national-insurance-class-4": [national_insurance]}),
    ]
    merged = _registry()._merge_uk_efrs_reports(separate)
    _assert_public_diagnostics(merged, first + second)
    assert [allowance, national_insurance] == before


def test_uk_stopped_result_keeps_both_error_and_ambiguity_evidence():
    result = _result("personal-allowance", 3)
    result.update({"executed": False, "error": "native run stopped"})
    report = _compare({"personal-allowance": [result]})
    _assert_public_diagnostics(report, 3)
    assert report["compared_values"] == 0
    assert report["errors"][0]["error"] == "native run stopped"


def test_uk_report_omits_empty_relation_diagnostics():
    result = _result("personal-allowance", 0)
    report = _compare({"personal-allowance": [result]})
    assert "relation_binding_diagnostics" not in json.dumps(report)
